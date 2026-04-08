"""Price history container (oldest bar first)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class PriceBar:
    day: date
    close: float


@dataclass
class PriceHistory:
    """Per-ticker daily price series. Oldest first."""

    bars: dict[str, list[PriceBar]] = field(default_factory=dict)

    def add_series(self, ticker: str, closes: list[tuple[date, float]]) -> None:
        self.bars[ticker.upper()] = [PriceBar(d, c) for d, c in closes]

    def closes(self, ticker: str) -> list[float]:
        return [b.close for b in self.bars.get(ticker.upper(), [])]

    def last(self, ticker: str) -> Optional[float]:
        seq = self.bars.get(ticker.upper())
        return seq[-1].close if seq else None

    def window(self, ticker: str, days: int) -> list[float]:
        seq = self.closes(ticker)
        return seq[-days:] if len(seq) >= days else seq
