"""Walk-forward backtest of the event scoring engine.

Approach
--------
1. Fetch price history long enough to cover `start`..`end` + a forward window.
2. For each trading day `d` in [start, end]:
     - Truncate the PriceHistory to just the bars available on/before `d`.
     - Call `score_events(..., as_of=d)`.
     - For every BUY recommendation on a ticker with enough forward price
       data, open a phantom position: enter at the close of `d`, exit at
       the close of `d + forward_window` trading days (or the event date
       + `forward_window`, whichever is later).
3. Aggregate hit rate, average return, total return, max drawdown.

Limitations
-----------
- News is only available *now*, so the backtest treats sentiment as constant
  (the feed you pass in). That biases results — real news is leakage-free
  only when recorded historically. The runner accepts a `news_as_of` hook
  so callers can plug in a historical news provider if they build one.
- Macro shock is computed once from the same feed for the same reason.
- Uses close-to-close returns; no slippage, no fees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

from ..config import DEFAULT_CONFIG, SimConfig
from ..events.calendar import EventCalendar
from ..events.models import Event
from ..news.feed import NewsFeed
from ..pricing.history import PriceHistory, PriceBar
from ..signals import Action, Recommendation, score_events


NewsProvider = Callable[[date], NewsFeed]


@dataclass
class BacktestTrade:
    ticker: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    score: float
    event_description: str

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price

    @property
    def is_winner(self) -> bool:
        return self.exit_price > self.entry_price


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    start: Optional[date] = None
    end: Optional[date] = None

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def hit_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.is_winner) / len(self.trades)

    @property
    def avg_return(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.return_pct for t in self.trades) / len(self.trades)

    @property
    def total_return(self) -> float:
        """Sum of per-trade returns (equal-weight, not compounded)."""
        return sum(t.return_pct for t in self.trades)

    @property
    def best(self) -> Optional[BacktestTrade]:
        return max(self.trades, key=lambda t: t.return_pct, default=None)

    @property
    def worst(self) -> Optional[BacktestTrade]:
        return min(self.trades, key=lambda t: t.return_pct, default=None)

    def summary(self) -> str:
        if not self.trades:
            return "no trades"
        lines = [
            f"backtest {self.start} -> {self.end}",
            f"  trades:       {self.n}",
            f"  hit rate:     {self.hit_rate * 100:.1f}%",
            f"  avg return:   {self.avg_return * 100:+.2f}%",
            f"  total return: {self.total_return * 100:+.2f}% (equal-weight, uncompounded)",
        ]
        if self.best:
            lines.append(
                f"  best:  {self.best.ticker} {self.best.entry_date} -> {self.best.exit_date} "
                f"({self.best.return_pct * 100:+.2f}%)"
            )
        if self.worst:
            lines.append(
                f"  worst: {self.worst.ticker} {self.worst.entry_date} -> {self.worst.exit_date} "
                f"({self.worst.return_pct * 100:+.2f}%)"
            )
        return "\n".join(lines)


def _slice_history(full: PriceHistory, as_of: date) -> PriceHistory:
    sliced = PriceHistory()
    for ticker, bars in full.bars.items():
        kept = [b for b in bars if b.day <= as_of]
        if kept:
            sliced.bars[ticker] = kept
    return sliced


def _bar_on_or_after(bars: list[PriceBar], target: date) -> Optional[PriceBar]:
    for b in bars:
        if b.day >= target:
            return b
    return None


def run_backtest(
    calendar: EventCalendar,
    full_history: PriceHistory,
    feed: NewsFeed,
    *,
    start: date,
    end: date,
    forward_window_days: int = 5,
    config: SimConfig = DEFAULT_CONFIG,
    news_provider: Optional[NewsProvider] = None,
) -> BacktestResult:
    """Walk each trading day from start to end and collect forward returns
    on every BUY recommendation the engine emits.

    If `news_provider` is supplied, it's called with the as-of date to
    fetch a point-in-time news feed (use this to avoid look-ahead bias).
    Otherwise `feed` is reused on every step (biased — see module docstring).
    """
    result = BacktestResult(start=start, end=end)

    # Trading days = days where at least one watched ticker has a price bar.
    all_days: set[date] = set()
    for bars in full_history.bars.values():
        for b in bars:
            if start <= b.day <= end:
                all_days.add(b.day)
    trading_days = sorted(all_days)

    seen_events: set[tuple[str, date, str]] = set()

    for d in trading_days:
        sliced = _slice_history(full_history, d)
        feed_today = news_provider(d) if news_provider else feed
        recs = score_events(
            calendar, feed_today, sliced, config=config, as_of=d
        )
        for r in recs:
            if r.action != Action.BUY or not r.event.ticker:
                continue
            key = (r.event.ticker, r.event.event_date, r.event.event_type.value)
            if key in seen_events:
                continue  # only enter each event once
            ticker = r.event.ticker
            bars = full_history.bars.get(ticker.upper(), [])
            entry_bar = _bar_on_or_after(bars, d)
            if entry_bar is None:
                continue
            # Exit: close `forward_window_days` trading days past the event.
            exit_target = max(r.event.event_date, entry_bar.day) + timedelta(
                days=forward_window_days
            )
            exit_bar = _bar_on_or_after(bars, exit_target)
            if exit_bar is None or exit_bar.day > end + timedelta(days=forward_window_days + 7):
                continue
            result.trades.append(
                BacktestTrade(
                    ticker=ticker,
                    entry_date=entry_bar.day,
                    exit_date=exit_bar.day,
                    entry_price=entry_bar.close,
                    exit_price=exit_bar.close,
                    score=r.score,
                    event_description=r.event.description,
                )
            )
            seen_events.add(key)

    return result
