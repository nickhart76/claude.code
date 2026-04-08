"""Central config. Keeps tunable knobs in one place."""

from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "stock_sim.sqlite3"


@dataclass
class ScoringWeights:
    """Weights for combining signals into a final event score.

    All weights are applied to signals in [-1, 1] or [0, 1].
    """

    event_impact: float = 0.40        # how historically impactful this event type is
    sentiment: float = 0.25           # aggregated news sentiment on the ticker
    macro_shock: float = 0.15         # negative global news drag
    not_priced_in: float = 0.20       # inverse of "market already reacted" score


@dataclass
class SimConfig:
    starting_cash: float = 100_000.0
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    # Minimum score [0, 1] required before showing a BUY recommendation.
    buy_threshold: float = 0.55
    sell_threshold: float = -0.25
    # How many days out to look when building the calendar.
    calendar_horizon_days: int = 21
    # Tickers to watch for ticker-specific events + news.
    watchlist: tuple[str, ...] = (
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
        "MRNA", "PFE", "XOM", "JPM", "AMD",
    )


DEFAULT_CONFIG = SimConfig()
