from datetime import date, datetime, timezone, timedelta

from stock_sim.config import SimConfig
from stock_sim.events.calendar import EventCalendar
from stock_sim.events.models import Event, EventType
from stock_sim.news.feed import NewsFeed
from stock_sim.news.models import NewsItem
from stock_sim.pricing.history import PriceHistory
from stock_sim.signals import Action, score_events


def _ev(ticker, days, direction=1, et=EventType.EARNINGS):
    return Event(
        ticker=ticker,
        event_type=et,
        event_date=date.today() + timedelta(days=days),
        description=f"{ticker} {et.value}",
        expected_direction=direction,
    )


def _flat_closes(n=40, start=100.0):
    return [(date.today() - timedelta(days=n - i), start + (i % 2) * 0.05) for i in range(n)]


def test_strong_positive_news_produces_buy():
    cal = EventCalendar([_ev("AAPL", 3)])
    feed = NewsFeed()
    now = datetime.now(timezone.utc)
    feed.add(NewsItem("Apple beats estimates, record blockbuster growth", now, "r", "AAPL"))
    feed.add(NewsItem("Analysts upgrade Apple on strong partnership wins", now, "r", "AAPL"))
    prices = PriceHistory()
    prices.add_series("AAPL", _flat_closes())
    config = SimConfig(buy_threshold=0.3)
    recs = score_events(cal, feed, prices, config=config)
    assert recs
    aapl = [r for r in recs if r.ticker == "AAPL"][0]
    assert aapl.action == Action.BUY
    assert aapl.score > 0


def test_bearish_news_does_not_buy():
    cal = EventCalendar([_ev("PFE", 5, direction=-1)])
    feed = NewsFeed()
    now = datetime.now(timezone.utc)
    feed.add(NewsItem("Pfizer warns weak quarter, layoffs, downgrade, lawsuit", now, "r", "PFE"))
    prices = PriceHistory()
    prices.add_series("PFE", _flat_closes())
    recs = score_events(cal, feed, prices)
    assert recs
    pfe = [r for r in recs if r.ticker == "PFE"][0]
    assert pfe.action != Action.BUY


def test_macro_shock_drags_score_down():
    cal = EventCalendar([_ev("AAPL", 3)])
    now = datetime.now(timezone.utc)
    feed_calm = NewsFeed()
    feed_calm.add(NewsItem("Apple beats estimates, record growth", now, "r", "AAPL"))
    feed_scared = NewsFeed()
    feed_scared.add(NewsItem("Apple beats estimates, record growth", now, "r", "AAPL"))
    for _ in range(4):
        feed_scared.add(NewsItem("war escalation sanctions", now, "r", None))
    prices = PriceHistory()
    prices.add_series("AAPL", _flat_closes())
    calm = score_events(cal, feed_calm, prices)[0].score
    scared = score_events(cal, feed_scared, prices)[0].score
    assert scared < calm
