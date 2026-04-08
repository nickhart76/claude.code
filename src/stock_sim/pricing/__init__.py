"""Price history and the priced-in detector."""

from .history import PriceHistory, PriceBar
from .priced_in import priced_in_score

__all__ = [
    "PriceHistory",
    "PriceBar",
    "fetch_history",
    "fetch_last_price",
    "priced_in_score",
]


def fetch_history(tickers, period="3mo"):
    from .providers import fetch_history as _impl
    return _impl(tickers, period=period)


def fetch_last_price(ticker):
    from .providers import fetch_last_price as _impl
    return _impl(ticker)
