"""Scheduled market-moving events: earnings, FDA decisions, Fed meetings, etc."""

from .models import Event, EventType
from .calendar import EventCalendar

__all__ = ["Event", "EventType", "EventCalendar", "build_calendar"]


def build_calendar(tickers):
    """Lazy re-export of providers.build_calendar so importing this
    package doesn't require yfinance/pandas."""
    from .providers import build_calendar as _impl

    return _impl(tickers)
