"""test_events.py — unit tests for the Stage 1 cockpit-redesign event log
(db.py's record_event/list_events; see
docs/developer/design/cockpit-redesign-spec.md §4/§14/§16).

Wiring tests (does start_run/stop_run/abort_running_runs/
advance_run_segment/record_uplink_for_run write the right event, at the
right trigger point, and survive a write failure) live next to those
methods in test_db.py. This file covers the generic event-log API itself:
insertion, keyset pagination (including the last-page edge case), filters,
and the record_event/list_events contract in isolation from any particular
caller.

Every test gets its own temp SQLite file — no shared state, no /data
dependency, no ChirpStack/MQTT involved.
"""
import os
import tempfile

from app.db import EVENT_LOG_MAX_LIMIT, Database


def _new_db() -> Database:
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    d = Database(path)
    d.init_schema()
    return d


def _make_run_row(d: Database, node_id: int) -> int:
    """event.run_id has a real FK on run(id) — tests that exercise run_id
    need an actual run row. Inserted directly via SQL rather than through
    start_run(), which (see test_db.py) already emits its own run_started
    event; this file tests record_event/list_events as a generic API,
    decoupled from that wiring."""
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    cur = d._conn.execute(
        "INSERT INTO run (device_node_id, device_placement_id, gateway_placement_id, "
        "phase, started_at, status, packets) VALUES (?, ?, ?, 'adr', ?, 'running', 0)",
        (node_id, dp, gp, d._now()),
    )
    d._conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------


def test_record_event_minimal_call_defaults_source_to_live():
    d = _new_db()
    event_id = d.record_event("join")
    assert event_id > 0
    event = d.list_events()["events"][0]
    assert event["type"] == "join"
    assert event["node_id"] is None
    assert event["run_id"] is None
    assert event["payload"] is None
    assert event["source"] == "live"
    assert event["ts"]  # non-empty UTC ISO timestamp


def test_record_event_stores_node_run_and_payload():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    run_id = _make_run_row(d, node_id)
    d.record_event("first_uplink", node_id=node_id, run_id=run_id, payload={"sf": 9})
    event = d.list_events()["events"][0]
    assert event["node_id"] == node_id
    assert event["run_id"] == run_id
    assert event["payload"] == {"sf": 9}


def test_record_event_can_mark_source_backfill():
    d = _new_db()
    d.record_event("run_started", source="backfill")
    event = d.list_events()["events"][0]
    assert event["source"] == "backfill"


def test_record_event_returns_incrementing_ids():
    d = _new_db()
    id1 = d.record_event("join")
    id2 = d.record_event("join")
    assert id2 > id1


# ---------------------------------------------------------------------------
# list_events — ordering, shape, node_name join
# ---------------------------------------------------------------------------


def test_list_events_empty_db():
    d = _new_db()
    result = d.list_events()
    assert result == {"events": [], "next_cursor": None, "has_more": False}


def test_list_events_orders_newest_first():
    d = _new_db()
    id1 = d.record_event("join")
    id2 = d.record_event("run_started")
    id3 = d.record_event("run_stopped")
    ids = [e["id"] for e in d.list_events()["events"]]
    assert ids == [id3, id2, id1]


def test_list_events_joins_node_name():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "thermostat-katia", "aaaa000000000001")
    d.record_event("join", node_id=node_id)
    event = d.list_events()["events"][0]
    assert event["node_name"] == "thermostat-katia"


def test_list_events_node_name_none_when_node_id_is_none():
    d = _new_db()
    d.record_event("run_started")
    event = d.list_events()["events"][0]
    assert event["node_id"] is None
    assert event["node_name"] is None


# ---------------------------------------------------------------------------
# Keyset pagination — WHERE id < cursor ORDER BY id DESC LIMIT n, never OFFSET
# ---------------------------------------------------------------------------


def test_list_events_keyset_pagination_across_two_pages():
    d = _new_db()
    ids = [d.record_event("join") for _ in range(5)]

    page1 = d.list_events(limit=2)
    assert [e["id"] for e in page1["events"]] == [ids[4], ids[3]]
    assert page1["has_more"] is True
    assert page1["next_cursor"] == ids[3]

    page2 = d.list_events(cursor=page1["next_cursor"], limit=2)
    assert [e["id"] for e in page2["events"]] == [ids[2], ids[1]]
    assert page2["has_more"] is True
    assert page2["next_cursor"] == ids[1]


def test_list_events_last_page_has_more_false_and_next_cursor_none():
    """The edge case: the last page must not claim there is more, and must
    not hand back a cursor that would return an empty page."""
    d = _new_db()
    ids = [d.record_event("join") for _ in range(3)]

    page1 = d.list_events(limit=2)
    page2 = d.list_events(cursor=page1["next_cursor"], limit=2)

    assert [e["id"] for e in page2["events"]] == [ids[0]]
    assert page2["has_more"] is False
    assert page2["next_cursor"] is None


def test_list_events_cursor_past_the_end_returns_empty_last_page():
    d = _new_db()
    first_id = d.record_event("join")
    result = d.list_events(cursor=first_id)
    assert result == {"events": [], "next_cursor": None, "has_more": False}


def test_list_events_exact_multiple_of_limit_has_more_false():
    """N rows, limit=N — must not claim a phantom extra page."""
    d = _new_db()
    for _ in range(4):
        d.record_event("join")
    result = d.list_events(limit=4)
    assert len(result["events"]) == 4
    assert result["has_more"] is False
    assert result["next_cursor"] is None


def test_list_events_limit_is_clamped_to_max():
    d = _new_db()
    for _ in range(3):
        d.record_event("join")
    result = d.list_events(limit=EVENT_LOG_MAX_LIMIT + 1000)
    assert len(result["events"]) == 3  # did not blow up / misbehave


def test_list_events_limit_clamped_to_at_least_one():
    d = _new_db()
    d.record_event("join")
    d.record_event("run_started")
    result = d.list_events(limit=0)
    assert len(result["events"]) == 1


# ---------------------------------------------------------------------------
# Filters — type / node_id / run_id
# ---------------------------------------------------------------------------


def test_list_events_filters_by_type():
    d = _new_db()
    d.record_event("join")
    d.record_event("run_started")
    d.record_event("run_started")
    result = d.list_events(type_="run_started")
    assert len(result["events"]) == 2
    assert all(e["type"] == "run_started" for e in result["events"])


def test_list_events_filters_by_node_id():
    d = _new_db()
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    n2, _ = d.upsert_node("device", "d2", "bbbb000000000002")
    d.record_event("join", node_id=n1)
    d.record_event("join", node_id=n2)
    result = d.list_events(node_id=n1)
    assert len(result["events"]) == 1
    assert result["events"][0]["node_id"] == n1


def test_list_events_filters_by_run_id():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    run1 = _make_run_row(d, node_id)
    run2 = _make_run_row(d, node_id)
    d.record_event("run_started", run_id=run1)
    d.record_event("run_stopped", run_id=run1)
    d.record_event("run_started", run_id=run2)
    result = d.list_events(run_id=run1)
    assert len(result["events"]) == 2
    assert all(e["run_id"] == run1 for e in result["events"])


def test_list_events_filters_combine_with_pagination():
    d = _new_db()
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    ids = [d.record_event("join", node_id=n1) for _ in range(3)]
    d.record_event("run_started", node_id=n1)  # different type — must be excluded

    page = d.list_events(type_="join", node_id=n1, limit=2)
    assert [e["id"] for e in page["events"]] == [ids[2], ids[1]]
    assert page["has_more"] is True


def test_list_events_no_match_returns_empty_not_error():
    d = _new_db()
    d.record_event("join")
    result = d.list_events(type_="gateway_moved")
    assert result == {"events": [], "next_cursor": None, "has_more": False}
