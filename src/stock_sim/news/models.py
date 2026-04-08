"""News domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Sentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class NewsItem:
    headline: str
    published_at: datetime  # tz-aware (UTC)
    source: str
    ticker: Optional[str] = None  # None = global/macro
    url: Optional[str] = None
    summary: str = ""

    @property
    def is_macro(self) -> bool:
        return self.ticker is None
