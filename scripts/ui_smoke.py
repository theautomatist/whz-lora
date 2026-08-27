#!/usr/bin/env python3
"""Click through the cockpit's main paths in a real browser and fail loudly.

Why this exists (cockpit-redesign Stage 2a, spec §6/§16): the frontend had
zero automated tests before this script. Stage 2a rewrote app.js from one
file full of inline `onclick`/`onchange` handlers into ES modules — a change
that is supposed to be invisible. The specific way that kind of refactor
breaks is silent: once module scope replaces the global `window` functions
an inline handler called, the handler doesn't error at page load — it just
throws a ReferenceError the moment someone taps the button, and the button
quietly does nothing. A human clicking around would eventually notice; a
`pytest` suite that never opens a browser never will.

Stage 2b (spec §7–§13/§20) rebuilt the navigation itself — a bottom tab bar
(Devices/Events/Radio/Map) plus two level-2 screens (device detail, opened
from a Devices card; measurement history, opened from a link on the
Devices tab) replacing the old header Live/History/Map/Events switch. This
script's checks were rewritten to match: they exercise the new tab bar, the
light/dark toggle, the RF vendor long-tail disclosure, and the event-log
search box, alongside everything the previous stage already covered.

This script is the net that catches that class of defect, and everything
else that only shows up once the interface actually renders and runs (see
`ui_audit.py`'s module docstring for the sibling story on layout). It drives
the real UI end to end and treats any JavaScript error or failed HTTP
response as a hard failure, not just missing content — that is the whole
point: a page can look fine and still be silently broken underneath.

What it checks, against a running instance:
  * every tab (Devices/Events/Radio/Map) is reachable and shows its lead
    content; each view carries zero horizontal overflow (spec Acceptance #3)
  * tapping a Devices card opens the device detail screen and fills it;
    the back button returns to Devices
  * the "All measurement history" link opens History; its back button
    returns to Devices
  * the light/dark toggle flips `<html data-theme>` and persists across a
    reload
  * the event log loads; the search box and the type filter chips narrow
    it; "Load more" is exercised when the current data actually offers a
    next page
  * the RF panel renders its sections, including the vendor KPI highlights;
    the long-tail disclosure expands and its own search narrows it
  * the floor plan and at least one placement photo actually load
    (`naturalWidth > 0` — a broken `<img src>` still "renders", just blank)
  * zero JavaScript errors and zero failed HTTP responses (>=400) over the
    whole run — this is the most important check, because it is exactly
    how a stale global-function handler shows up

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

TABS = ("devices", "events", "radio", "map")
VIEW_IDS = {
    "devices": "view-devices",
    "events":  "view-events",
    "radio":   "view-radio",
    "map":     "view-map",
    "detail":  "view-detail",
    "history": "view-history",
}


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


def _check_overflow(page, view: str, failures: list[str]) -> None:
    """scrollWidth must equal clientWidth on every view (Acceptance #3) —
    the 34 px overflow the pre-redesign header caused on every screen."""
    o = page.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
    if o["sw"] > o["cw"]:
        failures.append(f"{view}: horizontal overflow of {o['sw'] - o['cw']}px (scrollWidth {o['sw']} > clientWidth {o['cw']})")


def _switch_tab(page, tab: str, failures: list[str]) -> None:
    """Click a bottom-tab-bar button and confirm both halves of the switch:
    the target view appears AND every sibling view actually disappears —
    a CSS specificity fight can leave a hidden-looking element rendering
    underneath just fine, with no JavaScript error at all."""
    btn = page.query_selector(f'.tab-btn[data-tab="{tab}"]')
    if not btn:
        failures.append(f"tab button [data-tab={tab}] not found")
        return
    btn.click()
    page.wait_for_timeout(1200)
    view_id = VIEW_IDS[tab]
    view = page.query_selector(f"#{view_id}")
    if not view:
        failures.append(f"view container #{view_id} not found after clicking the {tab} tab")
        return
    if not view.is_visible():
        failures.append(f"#{view_id} did not become visible after clicking the {tab} tab")
    for other_tab, other_id in VIEW_IDS.items():
        if other_tab == tab:
            continue
        other = page.query_selector(f"#{other_id}")
        if other and other.is_visible():
            failures.append(f"#{other_id} is still visible after switching to {tab}")
    _check_overflow(page, tab, failures)


def _check_devices_view(page, failures: list[str]) -> None:
    """Devices is the default/landing tab — it must already carry at least
    one device/gateway card without any interaction, sorted by
    need-for-action (spec §7), and none of the five field nodes may be cut
    off (Acceptance #4)."""
    view = page.query_selector("#view-devices")
    if not view or not view.is_visible():
        failures.append("Devices view (#view-devices) is not visible on initial load")
        return
    cards = page.query_selector_all("#device-list .dcard")
    if not cards:
        failures.append("Devices list (#device-list) shows no device/gateway cards")
    _check_overflow(page, "devices", failures)


def _check_device_detail(page, failures: list[str]) -> None:
    """Tapping a Devices card must open the device-detail screen and fill
    it — the core of the whole field workflow (spec §7)."""
    card = page.query_selector("#device-list .dcard")
    if not card:
        failures.append("no Devices card to open (skipped device-detail check)")
        return
    card_name_el = card.query_selector(".dcard-name")
    card_name = (card_name_el.text_content() or "").strip() if card_name_el else ""
    card.click()
    page.wait_for_timeout(800)

    detail = page.query_selector("#view-detail")
    if not detail or not detail.is_visible():
        failures.append("tapping a Devices card did not open #view-detail")
        return
    _check_overflow(page, "detail", failures)

    name_after = (page.query_selector("#sel-name").text_content() or "").strip()
    if not name_after or name_after == "—":
        failures.append("opening a device left #sel-name empty/placeholder")
    if card_name and name_after != card_name:
        failures.append(
            f"opening the '{card_name}' card did not select it "
            f"(#sel-name reads '{name_after}')"
        )
    place_info = page.query_selector("#sel-place-info")
    if place_info is None or not (place_info.text_content() or "").strip():
        failures.append("#sel-place-info is empty after opening a device")

    back = page.query_selector("#detail-back-btn")
    if not back:
        failures.append("#detail-back-btn not found")
        return
    back.click()
    page.wait_for_timeout(600)
    devices_view = page.query_selector("#view-devices")
    if not devices_view or not devices_view.is_visible():
        failures.append("the detail back button did not return to #view-devices")


def _check_theme_toggle(page, failures: list[str]) -> None:
    """The light/dark toggle (spec §9/§20) must flip the <html data-theme>
    attribute and remember the choice across a reload."""
    btn = page.query_selector("#btn-theme-toggle")
    if not btn:
        failures.append("#btn-theme-toggle not found")
        return
    before = page.evaluate("document.documentElement.getAttribute('data-theme')")
    btn.click()
    page.wait_for_timeout(400)
    after = page.evaluate("document.documentElement.getAttribute('data-theme')")
    if after == before:
        failures.append(f"clicking the theme toggle did not change data-theme (stayed '{before}')")
        return
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1500)
    after_reload = page.evaluate("document.documentElement.getAttribute('data-theme')")
    if after_reload != after:
        failures.append(f"theme did not persist across reload (was '{after}', now '{after_reload}')")
    # Leave it back on light (the product-owner-decided default) for the
    # rest of the run, so later screenshots/checks see the default state.
    btn2 = page.query_selector("#btn-theme-toggle")
    if btn2 and page.evaluate("document.documentElement.getAttribute('data-theme')") != "light":
        btn2.click()
        page.wait_for_timeout(400)


def _check_history_view(page, failures: list[str]) -> None:
    """"All measurement history" (a link on the Devices tab, not a tab of
    its own — spec §11/§20) must open History and its back button must
    return to Devices."""
    _switch_tab(page, "devices", failures)
    link = page.query_selector("#btn-open-history")
    if not link:
        failures.append("#btn-open-history not found")
        return
    link.click()
    page.wait_for_timeout(1200)
    view = page.query_selector("#view-history")
    if not view or not view.is_visible():
        failures.append("#btn-open-history did not open #view-history")
        return
    _check_overflow(page, "history", failures)
    list_view = page.query_selector("#history-list-view")
    if list_view is None or not list_view.is_visible():
        failures.append("History did not land on its list view")
    body = page.query_selector("#history-list-body")
    text = (body.text_content() or "").strip() if body else ""
    if not text:
        failures.append("#history-list-body is empty (expected rows or an empty-state hint)")

    back = page.query_selector("#history-back-btn")
    if not back:
        failures.append("#history-back-btn not found")
        return
    back.click()
    page.wait_for_timeout(600)
    devices_view = page.query_selector("#view-devices")
    if not devices_view or not devices_view.is_visible():
        failures.append("the history back button did not return to #view-devices")


def _check_events_view(page, failures: list[str]) -> None:
    _switch_tab(page, "events", failures)
    body = page.query_selector("#events-log-body")
    if body is None:
        failures.append("#events-log-body not found")
        return
    text = (body.text_content() or "").strip()
    if not text:
        failures.append("#events-log-body is empty (expected rows or an empty-state hint)")

    # The search box (spec §12/§20.2 — "search exists nowhere" before this
    # stage) must actually narrow the list.
    search = page.query_selector("#evt-search")
    if search:
        rows_before = len(page.query_selector_all("#events-log-body .evt-row"))
        search.fill("zzz-no-such-event-zzz")
        page.wait_for_timeout(400)
        rows_after_noise = len(page.query_selector_all("#events-log-body .evt-row"))
        if rows_before and rows_after_noise != 0:
            failures.append("searching for a nonsense string did not empty the event list")
        search.fill("")
        page.wait_for_timeout(400)
        rows_after_clear = len(page.query_selector_all("#events-log-body .evt-row"))
        if rows_after_clear != rows_before:
            failures.append("clearing the event search did not restore the original rows")
    else:
        failures.append("#evt-search not found")

    # Filter chips must actually filter — pick a concrete type chip (not
    # "All types") if one is offered, and confirm the list re-renders. A
    # chip that silently does nothing is exactly the failure mode this
    # script exists to catch.
    type_chips = page.query_selector_all("#evt-type-chips .chip[data-evt-type]:not([data-evt-type=''])")
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

        all_chip = page.query_selector("#evt-type-chips .chip[data-evt-type='']")
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

    # A truncated row must be reachable by tap (spec §20.2 — a tooltip
    # alone is a desktop-only answer on a phone-first interface).
    first_row = page.query_selector("#events-log-body .evt-row")
    if first_row:
        first_row.click()
        page.wait_for_timeout(200)
        if not first_row.evaluate("el => el.classList.contains('evt-row-expanded')"):
            failures.append("tapping an event row did not expand it")


def _check_radio_view(page, failures: list[str]) -> None:
    _switch_tab(page, "radio", failures)

    for rf_id in (
        "rf-heatmap", "rf-timeline", "rf-sf-dist", "rf-rssi-dist",
        "rf-mtype-breakdown", "rf-networks", "rf-devices", "vendor-highlights",
        "rf-frame-log", "rf-sparkline",
    ):
        if page.query_selector(f"#{rf_id}") is None:
            failures.append(f"Radio section #{rf_id} is missing")

    # Vertical column charts (SF/RSSI distributions, product-owner addendum
    # 2026-08-26): every non-zero bucket must actually render a bar with a
    # real pixel height — the exact defect class flagged from the design
    # variants, where a `<span style="width:…%">` silently stayed 0 px wide
    # because inline elements ignore width/height. A genuine zero (SF11)
    # must render NO bar, not a sub-pixel one.
    # Measured in ONE page.evaluate rather than through element handles.
    # The RF panel replaces its innerHTML on every refresh (the 30 s ticker
    # and each SSE coex burst), so a handle taken a moment earlier can point
    # at a detached node by the time it is measured — which reported a real
    # 6 px bar as 0 px, and made `handle.bounding_box()` return None between
    # a truthiness check and its subscript. A snapshot taken inside the page
    # is atomic with respect to that re-render.
    for chart_id in ("rf-sf-dist", "rf-rssi-dist"):
        cols = page.evaluate(
            """(id) => {
              const root = document.getElementById(id);
              if (!root) return null;
              return [...root.querySelectorAll('.col-item')].map(col => {
                const fill = col.querySelector('.col-bar-fill');
                const label = col.querySelector('.col-label');
                const value = col.querySelector('.col-value');
                return {
                  isZero: col.classList.contains('col-zero'),
                  hasFill: !!fill,
                  height: fill ? fill.getBoundingClientRect().height : 0,
                  label: (label && label.textContent || '?').trim(),
                  hasValue: !!(value && value.textContent && value.textContent.trim()),
                };
              });
            }""",
            chart_id,
        )
        if not cols:
            failures.append(f"#{chart_id} rendered no .col-item columns")
            continue
        for col in cols:
            label = col["label"]
            if col["isZero"]:
                if col["hasFill"]:
                    failures.append(f"{chart_id}: zero column '{label}' still rendered a .col-bar-fill")
            elif not col["hasFill"]:
                failures.append(f"{chart_id}: non-zero column '{label}' rendered no .col-bar-fill")
            elif col["height"] < 3:
                failures.append(
                    f"{chart_id}: column '{label}' bar height is "
                    f"{col['height']:.1f}px (expected >= 3px floor)"
                )
            if not col["hasValue"]:
                failures.append(f"{chart_id}: column '{label}' has no visible value label above the bar")

    # The vendor long-tail disclosure (spec §19/§20.2) must expand and
    # mount its own searchable list.
    toggle = page.query_selector("#vendor-tail-toggle")
    if toggle and toggle.is_visible():
        toggle.click()
        page.wait_for_timeout(600)
        tail = page.query_selector("#vendor-tail")
        if not tail or not tail.is_visible():
            failures.append("the vendor 'Show more' disclosure did not reveal #vendor-tail")
        else:
            cells_before = len(page.query_selector_all("#lb-vendor-tail .vtail-cell"))
            search = page.query_selector("#lb-vendor-tail input[type=search]")
            if search:
                search.fill("zzz-no-such-oui")
                page.wait_for_timeout(400)
                cells_after = len(page.query_selector_all("#lb-vendor-tail .vtail-cell"))
                if cells_before and cells_after != 0:
                    failures.append("searching the vendor tail for a nonsense OUI did not empty it")
                search.fill("")
                page.wait_for_timeout(400)
            else:
                failures.append("no search input found inside the vendor tail")
    _check_overflow(page, "radio (vendor tail open)", failures)


def _check_map_view(page, failures: list[str]) -> None:
    _switch_tab(page, "map", failures)
    with_image = page.query_selector("#map-with-image")
    empty = page.query_selector("#map-empty")
    if with_image and with_image.is_visible():
        if not _wait_for_image_loaded(page, "#map-image"):
            failures.append("#map-image (floor plan) never reached naturalWidth > 0")
    elif not (empty and empty.is_visible()):
        failures.append("Map view shows neither #map-with-image nor #map-empty")


def _check_images_load(page, failures: list[str]) -> None:
    """At least one real placement photo must actually load — the device
    detail's photo strip (spec §10 removed the small Overview-card photo
    strip; the full-size collection now lives only in the detail screen)."""
    _switch_tab(page, "devices", failures)
    cards = page.query_selector_all("#device-list .dcard")
    photo = None
    for card in cards:
        node_id = card.get_attribute("data-node-id")
        if not node_id:
            continue
        card.click()
        page.wait_for_timeout(600)
        photo = page.query_selector("#sel-photos img")
        if photo:
            break
        back = page.query_selector("#detail-back-btn")
        if back:
            back.click()
            page.wait_for_timeout(300)
    if photo is None:
        failures.append("no placement photo found on any device's detail screen to verify loading")
        return
    if not _wait_for_image_loaded(page, "#sel-photos img"):
        failures.append("device-detail placement photo never reached naturalWidth > 0")
    back = page.query_selector("#detail-back-btn")
    if back:
        back.click()
        page.wait_for_timeout(300)


def _check_lightbox(page, failures: list[str]) -> None:
    """Tapping a placement photo must open it full size.

    The 72 px strip cannot tell two similar rooms apart, which is the one
    job a placement photo has. Worth a check of its own because the failure
    is quiet: the thumbnail still renders, it just stops responding, and
    nothing in the console says so.
    """
    page.click('.tab-btn[data-tab="devices"]')
    page.wait_for_timeout(800)
    btn = page.query_selector("#btn-open-history")
    if not btn:
        failures.append("no #btn-open-history to reach a run with photos")
        return
    btn.click()
    page.wait_for_timeout(1500)

    # Most placements carry no photo at all (3 of 11 in the real data), so
    # walk the rows until one actually has a strip rather than assuming.
    thumbs = []
    for row in page.query_selector_all("#history-list-body > *"):
        row.click()
        page.wait_for_timeout(1200)
        thumbs = page.query_selector_all("#hist-detail-device-photos .pthumb.view")
        if thumbs:
            break
        back = page.query_selector("#hist-detail-back-btn")
        if back:
            back.click()
            page.wait_for_timeout(600)
    if not thumbs:
        failures.append("no run in History exposed a placement photo to open")
        return

    thumbs[0].click()
    page.wait_for_timeout(400)
    if not page.evaluate("() => document.getElementById('photo-ov').classList.contains('open')"):
        failures.append("tapping a placement photo did not open the lightbox")
        return
    if not page.evaluate("() => document.body.classList.contains('scroll-locked')"):
        failures.append("lightbox is open but the page behind it still scrolls")

    if not _wait_for_image_loaded(page, "#photo-ov-img"):
        failures.append("#photo-ov-img never reached naturalWidth > 0")

    # Chevrons sit on a dark backdrop in both themes; .btn-o would resolve
    # them to near-black in the light theme and render them invisible.
    ink = page.evaluate(r"""() => {
      const e = document.getElementById('photo-ov-prev');
      if (!e || e.classList.contains('is-hidden')) return null;
      const c = (getComputedStyle(e).color.match(/\d+/g) || []).map(Number);
      const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
      const L = 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
      const bg = 0.2126 * f(6) + 0.7152 * f(10) + 0.0722 * f(14);
      return (Math.max(L, bg) + 0.05) / (Math.min(L, bg) + 0.05);
    }""")
    if ink is not None and ink < 4.5:
        failures.append(f"lightbox stepper is {ink:.1f}:1 against the backdrop (needs 4.5:1)")

    if len(thumbs) > 1:
        before = page.evaluate("() => document.getElementById('photo-ov-img').getAttribute('src')")
        page.click("#photo-ov-next")
        page.wait_for_timeout(900)
        after = page.evaluate("() => document.getElementById('photo-ov-img').getAttribute('src')")
        if before == after:
            failures.append("lightbox 'next' did not advance to another photo")

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    if page.evaluate("() => document.getElementById('photo-ov').classList.contains('open')"):
        failures.append("Escape did not close the lightbox")
    if page.evaluate("() => document.body.classList.contains('scroll-locked')"):
        failures.append("lightbox closed but left the page scroll-locked")


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
                if res.status >= 400
                else None,
            )

            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(3000)  # SSE connect + first /api/nodes render

            _check_devices_view(page, failures)
            _check_device_detail(page, failures)
            _check_theme_toggle(page, failures)
            _check_history_view(page, failures)
            _check_events_view(page, failures)
            _check_radio_view(page, failures)
            _check_map_view(page, failures)
            _check_images_load(page, failures)
            _check_lightbox(page, failures)

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
