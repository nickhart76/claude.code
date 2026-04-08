from datetime import datetime, timezone, timedelta

from stock_sim.news.feed import NewsFeed
from stock_sim.news.models import NewsItem
from stock_sim.news.sentiment import aggregate_sentiment, macro_shock_score, score_text


def _now():
    return datetime.now(timezone.utc)


def test_score_text_positive():
    assert score_text("Apple beats earnings in blockbuster quarter with record growth") > 0.2


def test_score_text_negative():
    assert score_text("Pfizer warns of weak quarter, plans layoffs, shares crash") < -0.2


def test_score_text_neutral():
    assert score_text("The company scheduled its quarterly call") == 0.0


def test_aggregate_sentiment_per_ticker():
    feed = NewsFeed()
    feed.add(NewsItem("Apple beats estimates, record growth", _now(), "r", "AAPL"))
    feed.add(NewsItem("Analysts upgrade Apple on strong demand", _now(), "r", "AAPL"))
    feed.add(NewsItem("Pfizer downgrade on weak guidance", _now(), "r", "PFE"))
    aapl = aggregate_sentiment(feed.items, "AAPL")
    pfe = aggregate_sentiment(feed.items, "PFE")
    assert aapl > 0
    assert pfe < 0


def test_macro_shock_triggers_on_war_terms():
    feed = NewsFeed()
    for _ in range(3):
        feed.add(NewsItem("Escalating war fears sanctions tighten", _now(), "r", None))
    feed.add(NewsItem("Quiet day in markets", _now(), "r", None))
    shock = macro_shock_score(feed.items)
    assert shock > 0.5
