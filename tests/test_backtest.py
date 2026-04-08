from datetime import date, timedelta

from stock_sim.backtest import run_backtest
from stock_sim.config import SimConfig
from stock_sim.events.calendar import EventCalendar
from stock_sim.events.models import Event, EventType
from stock_sim.news.feed import NewsFeed
from stock_sim.pricing.history import PriceBar, PriceHistory
from stock_sim.signals import Action


def _ramp_series(ticker: str, start: date, n: int, start_px: float, daily: float):
    bars = []
    px = start_px
    for i in range(n):
        bars.append((start + timedelta(days=i), px))
        px *= (1 + daily)
    return bars


def test_backtest_enters_on_buy_and_takes_forward_return():
    # 80 days of +0.5%/day growth for AAPL
    start_data = date(2024, 1, 1)
    closes = _ramp_series("AAPL", start_data, 80, 100.0, 0.005)
    prices = PriceHistory()
    prices.add_series("AAPL", closes)

    # Single earnings event mid-window.
    cal = EventCalendar(
        [
            Event(
                ticker="AAPL",
                event_type=EventType.EARNINGS,
                event_date=start_data + timedelta(days=40),
                description="AAPL earnings",
                expected_direction=1,
            )
        ]
    )

    feed = NewsFeed()  # no news = no sentiment boost; rely on impact weight
    # Relaxed threshold so the deterministic impact signal triggers a BUY.
    cfg = SimConfig(buy_threshold=-1.0)

    result = run_backtest(
        cal,
        prices,
        feed,
        start=start_data + timedelta(days=30),
        end=start_data + timedelta(days=50),
        forward_window_days=5,
        config=cfg,
    )

    assert result.n == 1
    trade = result.trades[0]
    assert trade.ticker == "AAPL"
    assert trade.return_pct > 0
    assert result.hit_rate == 1.0


def test_backtest_skips_without_forward_price_data():
    start_data = date(2024, 1, 1)
    closes = _ramp_series("AAPL", start_data, 20, 100.0, 0.01)  # too short
    prices = PriceHistory()
    prices.add_series("AAPL", closes)

    cal = EventCalendar(
        [
            Event(
                ticker="AAPL",
                event_type=EventType.EARNINGS,
                event_date=start_data + timedelta(days=15),
                description="AAPL earnings",
                expected_direction=1,
            )
        ]
    )
    cfg = SimConfig(buy_threshold=-1.0)
    result = run_backtest(
        cal,
        prices,
        NewsFeed(),
        start=start_data + timedelta(days=10),
        end=start_data + timedelta(days=19),
        forward_window_days=10,
        config=cfg,
    )
    assert result.n == 0


def test_backtest_summary_renders_without_trades():
    result = run_backtest(
        EventCalendar(),
        PriceHistory(),
        NewsFeed(),
        start=date(2024, 1, 1),
        end=date(2024, 1, 10),
    )
    assert result.summary() == "no trades"
