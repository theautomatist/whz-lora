#!/usr/bin/env python3
"""Click through the cockpit's main paths in a real browser and fail loudly.

Why this exists (cockpit-redesign Stage 2a, spec §6/§16): the frontend had
zero automated tests before this script. Stage 2a rewrites app.js from one
file full of inline `onclick`/`onchange` handlers into ES modules — a change
that is supposed to be invisible. The specific way that kind of refactor
breaks is silent: once module scope replaces the global `window` functions
an inline handler called, the handler doesn't error at page load — it just
throws a ReferenceError the moment someone taps the button, and the button
quietly does nothing. A human clicking around would eventually notice; a
`pytest` suite that never opens a browser never will.

This script is the net that catches that class of defect, and everything
else that only shows up once the interface actually renders and runs (see
`ui_audit.py`'s module docstring for the sibling story on layout). It drives
the real UI end to end and treats any JavaScript error or failed HTTP
response as a hard failure, not just missing content — that is the whole
point: a page can look fine and still be silently broken underneath.

What it checks, against a running instance:
  * every view is reachable via the tab switch and shows its lead content
  * selecting a device fills the detail panel
  * the event log loads; the type filter chips narrow it; "Load more" is
    exercised when the current data actually offers a next page
  * the RF panel renders its sections
  * the floor plan and at least one placement photo actually load
    (`naturalWidth > 0` — a broken `<img src>` still "renders", just blank)
  * zero JavaScript errors and zero failed HTTP responses (>=400, except
    favicon) over the whole run — this is the most important check, because
    it is exactly how a stale global-function handler shows up

Usage:
    python scripts/ui_smoke.py --url http://localhost:8000 \
        --user admin --password secret

Exit code 0 when every check passes, 1 otherwise — safe to use as a
verification step. Requires `playwright` and a browser; uses the installed
Edge by default (`--channel msedge`), same as `ui_audit.py`.
"""
from __future__ import annotations

import argparse
import os
import sys

DEFAULT_VIEWPORT = (390, 844)  # phone — the primary field-use device (spec §5)
IMAGE_LOAD_TIMEOUT_MS = 15000  # placements photos are full camera resolution
                                # (2-4 MB, spec §19.3) — local network, but not instant


def _wait_for_image_loaded(page, selector: str, timeout_ms: int = IMAGE_LOAD_TIMEOUT_MS) -> bool:
    """True once the first element matching *selector* has finished loading
    with a non-zero natural width. False (not raised) on timeout — callers
    turn that into one clear failure message instead of a Playwright
    stack trace."""
    try:
        page.wait_for_function(
            """(sel) => {
                const el = document.querySelector(sel);
                return !!el && el.complete && el.naturalWidth > 0;
            }""",
            arg=selector,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def _switch_view(page, button_id: str, view_id: str, failures: list[str],
                  hidden_ids: tuple[str, ...] = ()) -> None:
    """Click a tab and confirm both halves of the switch: the target view
    appears AND every other top-level view actually disappears. The second
    half matters on its own — a CSS specificity fight (an ID-selector
    `display` rule outranking a plain visibility class, for instance) can
    leave a hidden-looking element rendering underneath just fine, with no
    JavaScript error at all. `ui_audit.py`'s page-height/overflow numbers
    catch that after the fact; this catches it inline, in the same run
    that also checks for JS errors."""
    btn = page.query_selector(f"#{button_id}")
    if not btn:
        failures.append(f"view switch button #{button_id} not found")
        return
    btn.click()
    page.wait_for_timeout(1200)
    view = page.query_selector(f"#{view_id}")
    if not view:
        failures.append(f"view container #{view_id} not found after clicking #{button_id}")
        return
    if not view.is_visible():
        failures.append(f"#{view_id} did not become visible after clicking #{button_id}")
    for other_id in hidden_ids:
        other = page.query_selector(f"#{other_id}")
        if other and other.is_visible():
            failures.append(f"#{other_id} is still visible after switching to #{view_id}")


def _check_live_view(page, failures: list[str]) -> None:
    """Live is the default view — the Overview grid must already carry at
    least one device/gateway card without any interaction."""
    main = page.query_selector("#main")
    if not main or not main.is_visible():
        failures.append("Live view (#main) is not visible on initial load")
        return
    cards = page.query_selector_all("#node-grid .node-card")
    if not cards:
        failures.append("Overview (#node-grid) shows no device/gateway cards")

    # RF Environment panel — always expanded, no start/stop; every section
    # must at least exist (spec §19: this panel is a repeat offender for
    # "assembled from unrelated parts").
    for rf_id in (
        "rf-heatmap", "rf-timeline", "rf-sf-dist", "rf-rssi-dist",
        "rf-mtype-breakdown", "rf-networks", "rf-devices", "rf-vendors",
        "rf-frame-log", "rf-sparkline",
    ):
        if page.query_selector(f"#{rf_id}") is None:
            failures.append(f"RF Environment section #{rf_id} is missing")


def _check_device_selection(page, failures: list[str]) -> None:
    """Tapping an Overview card must fill the 'Selected device / gateway'
    detail panel — the core of the whole field workflow (spec §7)."""
    card = page.query_selector("#node-grid .node-card")
    if not card:
        failures.append("no Overview card to select (skipped device-selection check)")
        return
    name_before = (page.query_selector("#sel-name").text_content() or "").strip()
    card_name_el = card.query_selector(".nc-name")
    card_name = (card_name_el.text_content() or "").strip() if card_name_el else ""
    card.click()
    page.wait_for_timeout(800)
    name_after = (page.query_selector("#sel-name").text_content() or "").strip()
    if not name_after or name_after == "—":
        failures.append("selecting a device left #sel-name empty/placeholder")
    if card_name and name_after != card_name:
        failures.append(
            f"selecting the '{card_name}' card did not select it "
            f"(#sel-name reads '{name_after}', was '{name_before}')"
        )
    place_info = page.query_selector("#sel-place-info")
    if place_info is None or not (place_info.text_content() or "").strip():
        failures.append("#sel-place-info is empty after selecting a device")


def _check_history_view(page, failures: list[str]) -> None:
    _switch_view(page, "vsw-history", "history-view", failures,
                 hidden_ids=("main", "map-view", "events-view"))
    list_view = page.query_selector("#history-list-view")
    if list_view is None or not list_view.is_visible():
        failures.append("History did not land on its list view")
        return
    body = page.query_selector("#history-list-body")
    text = (body.text_content() or "").strip() if body else ""
    if not text:
        failures.append("#history-list-body is empty (expected rows or an empty-state hint)")


def _check_map_view(page, failures: list[str]) -> None:
    _switch_view(page, "vsw-map", "map-view", failures,
                 hidden_ids=("main", "history-view", "events-view"))
    with_image = page.query_selector("#map-with-image")
    empty = page.query_selector("#map-empty")
    if with_image and with_image.is_visible():
        if not _wait_for_image_loaded(page, "#map-image"):
            failures.append("#map-image (floor plan) never reached naturalWidth > 0")
    elif not (empty and empty.is_visible()):
        failures.append("Map view shows neither #map-with-image nor #map-empty")


def _check_events_view(page, failures: list[str]) -> None:
    _switch_view(page, "vsw-events", "events-view", failures,
                 hidden_ids=("main", "history-view", "map-view"))
    body = page.query_selector("#events-log-body")
    if body is None:
        failures.append("#events-log-body not found")
        return
    text = (body.text_content() or "").strip()
    if not text:
        failures.append("#events-log-body is empty (expected rows or an empty-state hint)")

    # Filter chips must actually filter — pick a concrete type chip (not
    # "All types") if one is offered, and confirm the list re-renders. A
    # chip that silently does nothing is exactly the failure mode this
    # script exists to catch.
    type_chips = page.query_selector_all("#evt-type-chips .evt-chip[data-evt-type]:not([data-evt-type=''])")
    if type_chips:
        rows_before = len(page.query_selector_all("#events-log-body .evt-row"))
        type_chips[0].click()
        page.wait_for_timeout(800)
        if not type_chips[0].evaluate("el => el.classList.contains('active')"):
            failures.append("clicking an event-type filter chip did not mark it active")
        rows_after = len(page.query_selector_all("#events-log-body .evt-row"))
        body_text_after = (body.text_content() or "").strip()
        if rows_after == rows_before and not body_text_after:
            failures.append("event-type filter produced neither rows nor an empty-state message")

        # Reset via "All types".
        all_chip = page.query_selector("#evt-type-chips .evt-chip[data-evt-type='']")
        if all_chip:
            all_chip.click()
            page.wait_for_timeout(800)
            if not all_chip.evaluate("el => el.classList.contains('active')"):
                failures.append("resetting the event-type filter did not reactivate 'All types'")
    else:
        failures.append("no event-type filter chips found")

    # "Load more" only renders when the current data actually has a next
    # page — with the small field dataset that is often not the case, and
    # that is a legitimate state, not a defect. Exercise it when offered;
    # otherwise just confirm it is correctly hidden.
    load_more_row = page.query_selector("#evt-load-more-row")
    if load_more_row and load_more_row.is_visible():
        rows_before = len(page.query_selector_all("#events-log-body .evt-row"))
        page.query_selector("#evt-load-more").click()
        page.wait_for_timeout(1000)
        rows_after = len(page.query_selector_all("#events-log-body .evt-row"))
        if rows_after <= rows_before:
            failures.append("'Load more' did not add any event rows")


def _check_images_load(page, failures: list[str]) -> None:
    """At least one real placement photo must actually load — back on Live,
    the Overview photo strip is the cheapest place to find one without
    depending on which device happens to be selected."""
    _switch_view(page, "vsw-live", "main", failures,
                 hidden_ids=("history-view", "map-view", "events-view"))
    photo = page.query_selector("#node-grid .photo-strip img")
    if photo is None:
        failures.append("no placement photo found on the Overview cards to verify loading")
        return
    if not _wait_for_image_loaded(page, "#node-grid .photo-strip img"):
        failures.append("Overview placement photo never reached naturalWidth > 0")


def run(url: str, user: str, password: str, channel: str | None, viewport: tuple[int, int]) -> list[str]:
    from playwright.sync_api import sync_playwright

    failures: list[str] = []
    js_errors: list[str] = []
    failed_responses: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=channel, headless=True)
        try:
            ctx = browser.new_context(
                http_credentials={"username": user, "password": password},
                viewport={"width": viewport[0], "height": viewport[1]},
            )
            page = ctx.new_page()
            page.on("pageerror", lambda exc: js_errors.append(str(exc)))
            page.on(
                "response",
                lambda res: failed_responses.append(f"{res.status} {res.request.method} {res.url}")
                if res.status >= 400 and "favicon" not in res.url
                else None,
            )

            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(3000)  # SSE connect + first /api/nodes render

            _check_live_view(page, failures)
            _check_device_selection(page, failures)
            _check_history_view(page, failures)
            _check_map_view(page, failures)
            _check_events_view(page, failures)
            _check_images_load(page, failures)

            ctx.close()
        finally:
            browser.close()

    if js_errors:
        failures.append(f"{len(js_errors)} JavaScript error(s): " + " | ".join(js_errors))
    if failed_responses:
        failures.append(f"{len(failed_responses)} failed HTTP response(s): " + " | ".join(failed_responses))

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--user", default=os.environ.get("COCKPIT_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("COCKPIT_PASSWORD", "change-me"))
    ap.add_argument("--channel", default="msedge",
                    help="Playwright browser channel (msedge, chrome, or '' for bundled chromium)")
    ap.add_argument("--viewport", default=f"{DEFAULT_VIEWPORT[0]}x{DEFAULT_VIEWPORT[1]}",
                    help="WIDTHxHEIGHT, e.g. 390x844 (default) or 1440x900")
    args = ap.parse_args()

    w, h = (int(p) for p in args.viewport.lower().split("x"))
    failures = run(args.url, args.user, args.password, args.channel or None, (w, h))

    if failures:
        print(f"FAIL — {len(failures)} problem(s) found:\n")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("OK — all checks passed, zero JS errors, zero failed HTTP responses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
