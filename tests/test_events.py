from datetime import date, timedelta

from stock_sim.events import EventCalendar
from stock_sim.events.models import Event, EventType


def _ev(ticker, days, et=EventType.EARNINGS, direction=1):
    return Event(
        ticker=ticker,
        event_type=et,
        event_date=date.today() + timedelta(days=days),
        description=f"{ticker} {et.value}",
        expected_direction=direction,
    )


def test_calendar_horizon_filter():
    cal = EventCalendar()
    cal.add(_ev("AAPL", 2))
    cal.add(_ev("NVDA", 30))
    cal.add(_ev("MSFT", -1))  # past
    upcoming = cal.upcoming(horizon_days=14)
    assert [e.ticker for e in upcoming] == ["AAPL"]


def test_calendar_ticker_filter_includes_macro():
    cal = EventCalendar()
    cal.add(_ev("AAPL", 2))
    cal.add(_ev("NVDA", 3))
    cal.add(_ev(None, 4, et=EventType.FED_MEETING, direction=0))
    upcoming = cal.upcoming(horizon_days=14, tickers=["AAPL"])
    tickers = [e.ticker for e in upcoming]
    assert "AAPL" in tickers
    assert None in tickers  # macro events pass through
    assert "NVDA" not in tickers


def test_baseline_impact_populated():
    ev = _ev("MRNA", 5, et=EventType.FDA_DECISION)
    assert ev.baseline_impact >= 0.8
