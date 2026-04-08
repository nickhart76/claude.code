"""Live news providers via RSS.

Uses free public RSS feeds — no API key required. Network required.

- Per-ticker news: Yahoo Finance per-symbol RSS
- Macro/world news: Reuters top news, AP top headlines, Yahoo Finance top
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import mktime
from typing import Iterable

from .feed import NewsFeed
from .models import NewsItem


YAHOO_TICKER_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

MACRO_FEEDS: list[tuple[str, str]] = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Reuters World", "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"),
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
]


def _parse_entry_time(entry) -> datetime:
    tup = entry.get("published_parsed") or entry.get("updated_parsed")
    if tup is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(mktime(tup), tz=timezone.utc)


def fetch_ticker_news(ticker: str) -> list[NewsItem]:
    """Fetch recent news for a ticker via Yahoo Finance RSS."""
    import feedparser

    t = ticker.upper()
    url = YAHOO_TICKER_RSS.format(ticker=t)
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"failed to fetch ticker RSS for {t}: {parsed.bozo_exception}")
    items: list[NewsItem] = []
    for entry in parsed.entries:
        items.append(
            NewsItem(
                headline=entry.get("title", ""),
                published_at=_parse_entry_time(entry),
                source="Yahoo Finance",
                ticker=t,
                url=entry.get("link"),
                summary=entry.get("summary", ""),
            )
        )
    return items


def fetch_macro_news() -> list[NewsItem]:
    """Fetch world/market-wide news from a set of RSS sources."""
    import feedparser

    items: list[NewsItem] = []
    for source, url in MACRO_FEEDS:
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            continue
        for entry in parsed.entries:
            items.append(
                NewsItem(
                    headline=entry.get("title", ""),
                    published_at=_parse_entry_time(entry),
                    source=source,
                    ticker=None,
                    url=entry.get("link"),
                    summary=entry.get("summary", ""),
                )
            )
    return items


def build_feed(tickers: Iterable[str]) -> NewsFeed:
    """Build a combined feed: per-ticker + macro news."""
    feed = NewsFeed()
    feed.extend(fetch_macro_news())
    for t in tickers:
        try:
            feed.extend(fetch_ticker_news(t))
        except RuntimeError:
            continue
    return feed
