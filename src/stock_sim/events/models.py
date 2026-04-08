"""Event domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    EARNINGS = "earnings"
    FDA_DECISION = "fda_decision"
    PRODUCT_LAUNCH = "product_launch"
    FED_MEETING = "fed_meeting"
    MACRO_DATA = "macro_data"         # CPI, jobs report, etc.
    GUIDANCE_UPDATE = "guidance_update"
    ANALYST_DAY = "analyst_day"


# Historical baseline impact for each event type, on a 0..1 scale.
# Calibrated from rough academic/industry observations; tune as you gather data.
DEFAULT_IMPACT: dict[EventType, float] = {
    EventType.EARNINGS: 0.75,
    EventType.FDA_DECISION: 0.90,
    EventType.PRODUCT_LAUNCH: 0.55,
    EventType.FED_MEETING: 0.70,
    EventType.MACRO_DATA: 0.50,
    EventType.GUIDANCE_UPDATE: 0.60,
    EventType.ANALYST_DAY: 0.40,
}


@dataclass(frozen=True)
class Event:
    ticker: Optional[str]        # None for macro events
    event_type: EventType
    event_date: date
    description: str
    # Optional pre-known directional bias from e.g. analyst consensus.
    expected_direction: int = 0  # -1 bearish, 0 neutral, +1 bullish

    @property
    def baseline_impact(self) -> float:
        return DEFAULT_IMPACT.get(self.event_type, 0.3)

    @property
    def is_macro(self) -> bool:
        return self.ticker is None
