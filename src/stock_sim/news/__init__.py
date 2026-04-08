"""News ingestion + sentiment scoring."""

from .models import NewsItem, Sentiment
from .sentiment import score_text, aggregate_sentiment, macro_shock_score
from .feed import NewsFeed

__all__ = [
    "NewsItem",
    "Sentiment",
    "score_text",
    "aggregate_sentiment",
    "macro_shock_score",
    "NewsFeed",
    "fetch_ticker_news",
    "fetch_macro_news",
    "build_feed",
]


def fetch_ticker_news(ticker):
    from .providers import fetch_ticker_news as _impl
    return _impl(ticker)


def fetch_macro_news():
    from .providers import fetch_macro_news as _impl
    return _impl()


def build_feed(tickers):
    from .providers import build_feed as _impl
    return _impl(tickers)
