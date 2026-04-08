"""Live event providers.

- Earnings dates: yfinance Ticker.calendar / get_earnings_dates.
- FOMC rate decisions and CPI/jobs releases: static schedule (Fed publishes
  the calendar years in advance). Extend FOMC_MEETINGS_* and MACRO_RELEASES_*
  as new years are published.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd

from .calendar import EventCalendar
from .models import Event, EventType


# FOMC meeting dates published at federalreserve.gov/monetarypolicy/fomccalendars.htm
# Only the *decision day* of each two-day meeting is listed.
FOMC_MEETINGS: list[date] = [
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 10, 29),
    date(2025, 12, 10),
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
]

# CPI release dates are published by BLS ~1 year ahead. Keep current + next month.
# Update these from bls.gov/schedule/news_release/cpi.htm as new months publish.
CPI_RELEASES: list[date] = [
    date(2026, 1, 14),
    date(2026, 2, 11),
    date(2026, 3, 12),
    date(2026, 4, 15),
    date(2026, 5, 13),
    date(2026, 6, 11),
    date(2026, 7, 15),
    date(2026, 8, 12),
    date(2026, 9, 11),
    date(2026, 10, 15),
    date(2026, 11, 13),
    date(2026, 12, 10),
]

# Nonfarm payrolls (first Friday each month, per BLS schedule).
NFP_RELEASES: list[date] = [
    date(2026, 1, 9),
    date(2026, 2, 6),
    date(2026, 3, 6),
    date(2026, 4, 3),
    date(2026, 5, 1),
    date(2026, 6, 5),
    date(2026, 7, 2),
    date(2026, 8, 7),
    date(2026, 9, 4),
    date(2026, 10, 2),
    date(2026, 11, 6),
    date(2026, 12, 4),
]


def fetch_earnings_events(tickers: Iterable[str]) -> list[Event]:
    """Pull upcoming earnings dates via yfinance.

    Network required. Raises RuntimeError on fetch failure.
    """
    import yfinance as yf

    out: list[Event] = []
    for t in tickers:
        t = t.upper()
        try:
            tk = yf.Ticker(t)
            df = tk.get_earnings_dates(limit=4)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"yfinance earnings fetch failed for {t}: {exc}") from exc
        if df is None or df.empty:
            continue
        today = date.today()
        for idx, _row in df.iterrows():
            if not isinstance(idx, (pd.Timestamp, datetime)):
                continue
            ev_day = idx.date() if hasattr(idx, "date") else idx
            if ev_day < today:
                continue
            out.append(
                Event(
                    ticker=t,
                    event_type=EventType.EARNINGS,
                    event_date=ev_day,
                    description=f"{t} earnings release",
                )
            )
    return out


def macro_events(as_of: date | None = None) -> list[Event]:
    today = as_of or date.today()
    out: list[Event] = []
    for d in FOMC_MEETINGS:
        if d >= today:
            out.append(Event(None, EventType.FED_MEETING, d, "FOMC rate decision"))
    for d in CPI_RELEASES:
        if d >= today:
            out.append(Event(None, EventType.MACRO_DATA, d, "CPI release"))
    for d in NFP_RELEASES:
        if d >= today:
            out.append(Event(None, EventType.MACRO_DATA, d, "Nonfarm payrolls"))
    return out


def build_calendar(tickers: Iterable[str]) -> EventCalendar:
    """Build a calendar combining live earnings + static macro schedule."""
    cal = EventCalendar()
    cal.extend(macro_events())
    cal.extend(fetch_earnings_events(tickers))
    return cal
