"""Live price providers via yfinance."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from .history import PriceHistory


def fetch_history(tickers: Iterable[str], period: str = "3mo") -> PriceHistory:
    """Fetch daily close history for a set of tickers.

    `period` accepts yfinance strings: 1mo, 3mo, 6mo, 1y, 2y, etc.
    Network required.
    """
    import yfinance as yf

    tickers = list(tickers)
    if not tickers:
        return PriceHistory()

    # yfinance.download handles multi-ticker efficiently.
    df = yf.download(
        tickers=" ".join(tickers),
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no price data for {tickers}")

    hist = PriceHistory()
    if len(tickers) == 1:
        t = tickers[0].upper()
        closes = [
            (idx.date(), float(row["Close"]))
            for idx, row in df.iterrows()
            if not _is_nan(row.get("Close"))
        ]
        hist.add_series(t, closes)
        return hist

    for t in tickers:
        t_up = t.upper()
        if t_up not in df.columns.get_level_values(0):
            continue
        sub = df[t_up]
        closes = [
            (idx.date(), float(row["Close"]))
            for idx, row in sub.iterrows()
            if not _is_nan(row.get("Close"))
        ]
        hist.add_series(t_up, closes)
    return hist


def fetch_last_price(ticker: str) -> Optional[float]:
    """Fetch the most recent close for a single ticker."""
    hist = fetch_history([ticker], period="5d")
    return hist.last(ticker)


def _is_nan(x) -> bool:
    try:
        return x != x  # NaN != NaN
    except Exception:  # noqa: BLE001
        return False
