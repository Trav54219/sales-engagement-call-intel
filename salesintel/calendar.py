"""Business-day arithmetic and send-window rules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

WEEKDAYS = frozenset({0, 1, 2, 3, 4})  # Monday=0


def is_business_day(d: date, holidays: Iterable[date] = ()) -> bool:
    return d.weekday() < 5 and d not in set(holidays)


def add_business_days(d: date, n: int, holidays: Iterable[date] = ()) -> date:
    """Move forward n business days. n=0 returns d unchanged (even on a weekend)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    hol = set(holidays)
    cur = d
    while n > 0:
        cur += timedelta(days=1)
        if is_business_day(cur, hol):
            n -= 1
    return cur


@dataclass(frozen=True)
class SendWindow:
    """Local-time window in which sends are allowed, on allowed weekdays."""

    start: time = time(9, 0)
    end: time = time(17, 0)
    days: frozenset = WEEKDAYS

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError("window start must be before end")
        if not self.days:
            raise ValueError("window needs at least one day")

    def next_slot(self, local: datetime, holidays: Iterable[date] = ()) -> datetime:
        """Earliest moment >= `local` inside the window (tz-aware datetime in, same tz out)."""
        hol = set(holidays)
        cur = local
        for _ in range(400):
            day_ok = cur.weekday() in self.days and cur.date() not in hol
            t = cur.timetz().replace(tzinfo=None)
            if day_ok and self.start <= t < self.end:
                return cur
            if day_ok and t < self.start:
                return cur.replace(hour=self.start.hour, minute=self.start.minute, second=0, microsecond=0)
            nxt = (cur + timedelta(days=1)).replace(
                hour=self.start.hour, minute=self.start.minute, second=0, microsecond=0
            )
            cur = nxt
        raise RuntimeError("no send slot found within 400 days")
