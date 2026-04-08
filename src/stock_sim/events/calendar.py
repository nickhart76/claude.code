"""Event calendar container: filter by horizon and ticker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from .models import Event


@dataclass
class EventCalendar:
    events: list[Event] = field(default_factory=list)

    def add(self, event: Event) -> None:
        self.events.append(event)

    def extend(self, events: Iterable[Event]) -> None:
        self.events.extend(events)

    def upcoming(
        self,
        *,
        as_of: Optional[date] = None,
        horizon_days: int = 21,
        tickers: Optional[Iterable[str]] = None,
    ) -> list[Event]:
        today = as_of or date.today()
        end = today + timedelta(days=horizon_days)
        ticker_set = {t.upper() for t in tickers} if tickers else None

        out = []
        for ev in self.events:
            if ev.event_date < today or ev.event_date > end:
                continue
            # Macro events (ticker=None) always pass the ticker filter.
            if (
                ticker_set is not None
                and ev.ticker
                and ev.ticker.upper() not in ticker_set
            ):
                continue
            out.append(ev)
        out.sort(key=lambda e: (e.event_date, e.ticker or ""))
        return out

    def for_ticker(self, ticker: str) -> list[Event]:
        t = ticker.upper()
        return [e for e in self.events if (e.ticker or "").upper() == t]
