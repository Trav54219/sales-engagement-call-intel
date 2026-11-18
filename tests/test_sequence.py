from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from salesintel.calendar import SendWindow, add_business_days
from salesintel.sequence import Engine, Prospect, Sequence, Step, Variant, pick_variant

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def v(n="A", w=1.0):
    return Variant(n, "s", "b", w)


def test_add_business_days_skips_weekend_and_holiday():
    fri = date(2026, 11, 20)
    assert add_business_days(fri, 1) == date(2026, 11, 23)  # Monday
    assert add_business_days(fri, 5) == date(2026, 11, 27)
    assert add_business_days(fri, 5, {date(2026, 11, 26)}) == date(2026, 11, 30)
    assert add_business_days(fri, 0) == fri


def test_window_pushes_to_next_open_slot():
    w = SendWindow()
    sat_noon = datetime(2026, 11, 21, 12, 0, tzinfo=NY)
    assert w.next_slot(sat_noon) == datetime(2026, 11, 23, 9, 0, tzinfo=NY)
    early = datetime(2026, 11, 23, 6, 30, tzinfo=NY)
    assert w.next_slot(early) == datetime(2026, 11, 23, 9, 0, tzinfo=NY)
    late = datetime(2026, 11, 23, 17, 0, tzinfo=NY)  # end is exclusive
    assert w.next_slot(late) == datetime(2026, 11, 24, 9, 0, tzinfo=NY)
    inside = datetime(2026, 11, 23, 10, 15, tzinfo=NY)
    assert w.next_slot(inside) == inside


def test_window_skips_holiday():
    w = SendWindow()
    wed = datetime(2026, 11, 25, 18, 0, tzinfo=NY)
    assert w.next_slot(wed, {date(2026, 11, 26)}) == datetime(2026, 11, 27, 9, 0, tzinfo=NY)


def test_invalid_sequences_rejected():
    with pytest.raises(ValueError):
        Sequence("x", ())
    with pytest.raises(ValueError):
        Sequence("x", (Step("a", 0, (v(),)), Step("a", 1, (v(),))))
    with pytest.raises(ValueError):
        Sequence("x", (Step("a", 0, (v(w=0),)),))
    with pytest.raises(ValueError):
        SendWindow(start=time(17), end=time(9))


def make_engine():
    seq = Sequence("t", (Step("s1", 0, (v("A"), v("B"))), Step("s2", 2, (v(),)), Step("s3", 1, (v(),))))
    return Engine(seq)


def test_schedule_uses_business_days_and_prospect_timezone():
    eng = make_engine()
    p = Prospect("p1", "p1@example.com", "America/New_York")
    # Thu 2026-11-19 14:00 UTC = 09:00 NY, inside window
    now = datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
    e = eng.enroll(p, now)
    assert e.next_due == now
    s1 = eng.tick(now)
    assert len(s1) == 1
    # +2 business days from Thu -> Mon 11-23, 09:00 NY = 14:00 UTC
    assert e.next_due == datetime(2026, 11, 23, 14, 0, tzinfo=UTC)
    assert eng.tick(datetime(2026, 11, 22, 14, 0, tzinfo=UTC)) == []
    assert len(eng.tick(datetime(2026, 11, 23, 14, 0, tzinfo=UTC))) == 1
    assert e.next_due == datetime(2026, 11, 24, 14, 0, tzinfo=UTC)


def test_enroll_outside_window_waits():
    eng = make_engine()
    sat = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)
    e = eng.enroll(Prospect("p", "p@example.com"), sat)
    assert e.next_due == datetime(2026, 11, 23, 14, 0, tzinfo=UTC)
    assert eng.tick(sat) == []


def test_stop_on_reply_prevents_further_sends():
    eng = make_engine()
    now = datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
    eng.enroll(Prospect("p1", "a@example.com"), now)
    eng.tick(now)
    assert eng.record_event("p1", "reply") == "replied"
    assert eng.tick(datetime(2027, 1, 1, tzinfo=UTC)) == []
    assert eng.enrollments["p1"].next_due is None


def test_bounce_and_unsubscribe_stop_but_reply_after_stop_does_not_override():
    eng = make_engine()
    now = datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
    eng.enroll(Prospect("p1", "a@example.com"), now)
    assert eng.record_event("p1", "unsubscribe") == "stopped"
    assert eng.record_event("p1", "reply") == "stopped"
    with pytest.raises(ValueError):
        eng.record_event("p1", "nonsense")


def test_sequence_completes_and_double_enroll_rejected():
    eng = make_engine()
    t = datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
    eng.enroll(Prospect("p1", "a@example.com"), t)
    with pytest.raises(ValueError):
        eng.enroll(Prospect("p1", "a@example.com"), t)
    sent = []
    for day in range(19, 32):
        sent += eng.tick(datetime(2026, 11, min(day, 30), 14, 0, tzinfo=UTC))
    assert [s.step_id for s in sent] == ["s1", "s2", "s3"]
    assert eng.enrollments["p1"].status == "completed"


def test_variant_assignment_deterministic_and_weighted():
    step = Step("s", 0, (v("A", 1), v("B", 1)))
    assert pick_variant(step, "x") == pick_variant(step, "x")
    names = [pick_variant(step, f"p{i}").name for i in range(2000)]
    share_a = names.count("A") / len(names)
    assert 0.45 < share_a < 0.55
    skew = Step("s", 0, (v("A", 9), v("B", 1)))
    share = [pick_variant(skew, f"p{i}").name for i in range(2000)].count("A") / 2000
    assert 0.86 < share < 0.94


def test_variant_report_attributes_reply_to_last_send():
    eng = make_engine()
    now = datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
    for i in range(10):
        eng.enroll(Prospect(f"p{i}", f"p{i}@example.com"), now)
    sent = eng.tick(now)
    first = sent[0]
    eng.record_event(first.prospect_id, "reply")
    rep = eng.variant_report()
    assert sum(r["sent"] for r in rep.values()) == 10
    assert rep[(first.step_id, first.variant)]["replied"] == 1
    assert sum(r["replied"] for r in rep.values()) == 1
