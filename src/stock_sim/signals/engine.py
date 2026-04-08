"""Signal scoring engine.

Combines four inputs per upcoming event into a single recommendation:

    final_score = w_impact * event_impact
                + w_sentiment * aggregated_news_sentiment
                - w_macro * macro_shock_score            (drag)
                + w_priced * (1 - priced_in_score)       (reward for untouched stocks)

Scale is roughly [-1, 1]. Positive -> BUY candidate, negative -> AVOID/SHORT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from ..config import DEFAULT_CONFIG, SimConfig
from ..events.calendar import EventCalendar
from ..events.models import Event
from ..news.feed import NewsFeed
from ..news.sentiment import aggregate_sentiment, macro_shock_score
from ..pricing.history import PriceHistory
from ..pricing.priced_in import priced_in_score


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    AVOID = "AVOID"


@dataclass
class Recommendation:
    event: Event
    action: Action
    score: float             # final score in roughly [-1, 1]
    sentiment: float         # -1..1
    priced_in: float         # 0..1
    macro_shock: float       # 0..1
    rationale: str

    @property
    def ticker(self) -> Optional[str]:
        return self.event.ticker

    @property
    def event_date(self) -> date:
        return self.event.event_date


def score_events(
    calendar: EventCalendar,
    feed: NewsFeed,
    prices: PriceHistory,
    *,
    config: SimConfig = DEFAULT_CONFIG,
    as_of: Optional[date] = None,
) -> list[Recommendation]:
    """Score every upcoming event in the calendar."""
    upcoming = calendar.upcoming(
        as_of=as_of, horizon_days=config.calendar_horizon_days
    )
    shock = macro_shock_score(feed.macro(hours=72))
    w = config.weights

    recs: list[Recommendation] = []
    for ev in upcoming:
        impact = ev.baseline_impact

        if ev.ticker:
            ticker_items = feed.recent(hours=96, ticker=ev.ticker)
            senti = aggregate_sentiment(ticker_items, ev.ticker)
            closes = prices.closes(ev.ticker)
            p_in = priced_in_score(
                closes,
                expected_direction=ev.expected_direction or 1,
            )
        else:
            senti = 0.0
            p_in = 0.0

        # For macro events impact contributes but direction is neutral.
        directional_impact = impact * (ev.expected_direction or 0)
        # If the event type is bullish-by-assumption and no direction set,
        # treat as mildly bullish so earnings still show up.
        if ev.ticker and ev.expected_direction == 0:
            directional_impact = impact * 0.3

        score = (
            w.event_impact * directional_impact
            + w.sentiment * senti
            - w.macro_shock * shock
            + w.not_priced_in * (1.0 - p_in)
            * (1.0 if directional_impact >= 0 else -1.0)
        )

        action = _decide(score, config)
        rationale = (
            f"impact={impact:.2f} dir={ev.expected_direction:+d} "
            f"sentiment={senti:+.2f} priced_in={p_in:.2f} shock={shock:.2f}"
        )
        recs.append(
            Recommendation(
                event=ev,
                action=action,
                score=score,
                sentiment=senti,
                priced_in=p_in,
                macro_shock=shock,
                rationale=rationale,
            )
        )

    recs.sort(key=lambda r: (r.event_date, -r.score))
    return recs


def _decide(score: float, config: SimConfig) -> Action:
    if score >= config.buy_threshold:
        return Action.BUY
    if score <= config.sell_threshold:
        return Action.AVOID
    return Action.HOLD
