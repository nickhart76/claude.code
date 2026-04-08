"""'Already priced in' detector.

The premise: if a stock has already run up significantly in the days before
an expected bullish event, much of the expected move is already reflected
in the price — so the incremental upside from the event itself is smaller.

This is a heuristic, not a model. It returns a 0..1 score where 1.0 means
"fully priced in" and 0.0 means "no pre-event drift detected".

Inputs considered:
- recent_drift:   cumulative log-return over the last `lookback` trading days
                  relative to typical daily volatility
- relative_move:  how large the drift is vs. the stock's own 60d volatility

We compare against `expected_direction`: if the drift aligns with the
expected direction of the event, the priced-in score rises.
"""

from __future__ import annotations

import math
from typing import Sequence


def _log_returns(closes: Sequence[float]) -> list[float]:
    out = []
    for prev, cur in zip(closes, closes[1:]):
        if prev <= 0 or cur <= 0:
            continue
        out.append(math.log(cur / prev))
    return out


def _stdev(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def priced_in_score(
    closes: Sequence[float],
    *,
    expected_direction: int = 1,
    lookback: int = 10,
) -> float:
    """Return a 0..1 score of how much an expected move appears priced in."""
    if len(closes) < lookback + 5:
        return 0.0

    recent = closes[-(lookback + 1):]
    recent_returns = _log_returns(recent)
    if not recent_returns:
        return 0.0

    long_returns = _log_returns(closes[-min(60, len(closes)):])
    vol = _stdev(long_returns)
    if vol <= 0:
        return 0.0

    cumulative = sum(recent_returns)
    # z-ish score: cumulative drift vs. expected noise over `lookback` days.
    expected_noise = vol * math.sqrt(lookback)
    z = cumulative / expected_noise if expected_noise > 0 else 0.0

    if expected_direction == 0:
        aligned = abs(z)
    else:
        aligned = z * expected_direction

    # Map aligned-z into 0..1, saturating around 2 sigma.
    if aligned <= 0:
        return 0.0
    return max(0.0, min(1.0, aligned / 2.0))
