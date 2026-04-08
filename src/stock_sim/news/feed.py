"""In-memory news feed container."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import NewsItem


@dataclass
class NewsFeed:
    items: list[NewsItem] = field(default_factory=list)

    def add(self, item: NewsItem) -> None:
        self.items.append(item)

    def extend(self, items: list[NewsItem]) -> None:
        self.items.extend(items)

    def recent(self, *, hours: int = 72, ticker: Optional[str] = None) -> list[NewsItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        t = ticker.upper() if ticker else None
        out = []
        for it in self.items:
            if it.published_at < cutoff:
                continue
            if t and (it.ticker or "").upper() != t:
                continue
            out.append(it)
        return out

    def macro(self, *, hours: int = 72) -> list[NewsItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [i for i in self.items if i.is_macro and i.published_at >= cutoff]
