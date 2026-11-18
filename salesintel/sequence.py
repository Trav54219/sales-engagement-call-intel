"""Sequence engine: steps, business-day delays, send windows, stop-on-reply, A/B variants."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .calendar import SendWindow, add_business_days

UTC = timezone.utc
TERMINAL = {"replied", "stopped", "completed"}
STOP_EVENTS = {"reply": "replied", "bounce": "stopped", "unsubscribe": "stopped"}


@dataclass(frozen=True)
class Variant:
    name: str
    subject: str
    body: str
    weight: float = 1.0


@dataclass(frozen=True)
class Step:
    id: str
    delay_business_days: int  # after the previous step was due (step 1: after enrollment)
    variants: tuple
    channel: str = "email"


@dataclass(frozen=True)
class Sequence:
    name: str
    steps: tuple
    window: SendWindow = field(default_factory=SendWindow)
    holidays: frozenset = frozenset()

    def __post_init__(self):
        if not self.steps:
            raise ValueError("sequence needs at least one step")
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("step ids must be unique")
        for s in self.steps:
            if s.delay_business_days < 0:
                raise ValueError(f"{s.id}: negative delay")
            if not s.variants:
                raise ValueError(f"{s.id}: needs at least one variant")
            if any(v.weight <= 0 for v in s.variants):
                raise ValueError(f"{s.id}: variant weights must be > 0")


@dataclass(frozen=True)
class Prospect:
    id: str
    email: str
    tz: str = "America/New_York"


@dataclass(frozen=True)
class Send:
    prospect_id: str
    step_id: str
    variant: str
    scheduled_for: datetime  # UTC


@dataclass
class Enrollment:
    prospect: Prospect
    next_index: int = 0
    next_due: Optional[datetime] = None
    status: str = "active"
    history: list = field(default_factory=list)


def pick_variant(step: Step, prospect_id: str) -> Variant:
    """Deterministic weighted assignment: same prospect+step always gets the same variant."""
    h = hashlib.sha256(f"{prospect_id}:{step.id}".encode()).digest()
    point = int.from_bytes(h[:8], "big") / 2**64 * sum(v.weight for v in step.variants)
    acc = 0.0
    for v in step.variants:
        acc += v.weight
        if point < acc:
            return v
    return step.variants[-1]


class Engine:
    def __init__(self, sequence: Sequence):
        self.seq = sequence
        self.enrollments: dict = {}

    def _due_time(self, base_utc: datetime, tz: str, delay: int) -> datetime:
        zone = ZoneInfo(tz)
        local = base_utc.astimezone(zone)
        day = add_business_days(local.date(), delay, self.seq.holidays)
        cand = datetime.combine(day, local.timetz().replace(tzinfo=None), tzinfo=zone)
        return self.seq.window.next_slot(cand, self.seq.holidays).astimezone(UTC)

    def enroll(self, prospect: Prospect, now: datetime) -> Enrollment:
        if prospect.id in self.enrollments:
            raise ValueError(f"{prospect.id} already enrolled")
        e = Enrollment(prospect)
        e.next_due = self._due_time(now, prospect.tz, self.seq.steps[0].delay_business_days)
        self.enrollments[prospect.id] = e
        return e

    def tick(self, now: datetime) -> list:
        """Return every send due at or before `now` and advance those enrollments one step."""
        out = []
        for e in self.enrollments.values():
            if e.status != "active" or e.next_due is None or e.next_due > now:
                continue
            step = self.seq.steps[e.next_index]
            v = pick_variant(step, e.prospect.id)
            send = Send(e.prospect.id, step.id, v.name, e.next_due)
            e.history.append({"send": send, "replied": False})
            out.append(send)
            e.next_index += 1
            if e.next_index >= len(self.seq.steps):
                e.status, e.next_due = "completed", None
            else:
                nxt = self.seq.steps[e.next_index]
                e.next_due = self._due_time(send.scheduled_for, e.prospect.tz, nxt.delay_business_days)
        return out

    def record_event(self, prospect_id: str, kind: str) -> str:
        """reply -> replied; bounce/unsubscribe -> stopped. Terminal states are not overwritten."""
        if kind not in STOP_EVENTS:
            raise ValueError(f"unknown event {kind!r}")
        e = self.enrollments[prospect_id]
        if kind == "reply" and e.history:
            e.history[-1]["replied"] = True  # attribute to the most recent send
        if e.status == "active" or (e.status == "completed" and kind == "reply"):
            e.status, e.next_due = STOP_EVENTS[kind], None
        return e.status

    def variant_report(self) -> dict:
        """Sends and replies per (step, variant). Raw counts only; no significance claim."""
        rep: dict = {}
        for e in self.enrollments.values():
            for h in e.history:
                key = (h["send"].step_id, h["send"].variant)
                r = rep.setdefault(key, {"sent": 0, "replied": 0})
                r["sent"] += 1
                r["replied"] += int(h["replied"])
        return rep
