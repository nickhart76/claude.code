"""Lightweight lexicon-based sentiment scoring.

This is intentionally simple and dependency-free so the project runs
anywhere. A production setup would swap this out for FinBERT or an LLM
classifier, but the interface below stays the same.
"""

from __future__ import annotations

import math
import re
from typing import Iterable

from .models import NewsItem


POSITIVE_TERMS = {
    "beat", "beats", "surge", "surges", "surged", "record", "record-high",
    "breakthrough", "approved", "approval", "upgrade", "upgraded", "bullish",
    "outperform", "strong", "strongest", "growth", "profitable", "expand",
    "expansion", "win", "wins", "partnership", "blockbuster", "raises",
    "raise", "buyback", "dividend-hike", "rally", "rallied", "rallies",
}

NEGATIVE_TERMS = {
    "miss", "missed", "misses", "plunge", "plunges", "plunged", "crash",
    "crashes", "crashed", "rejected", "rejection", "downgrade", "downgraded",
    "bearish", "underperform", "weak", "weakest", "decline", "declines",
    "recall", "lawsuit", "probe", "investigation", "fraud", "bankruptcy",
    "layoffs", "layoff", "cut", "cuts", "warning", "warn", "war", "conflict",
    "sanction", "sanctions", "shutdown", "default",
}

# Macro-shock terms get extra weight when attached to global (no ticker) news.
MACRO_SHOCK_TERMS = {
    "war", "invasion", "strike", "attack", "pandemic", "recession",
    "crash", "default", "shutdown", "rate-hike", "rate-hikes",
}


_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def score_text(text: str) -> float:
    """Return a sentiment score in [-1, 1] for a blob of text."""
    if not text:
        return 0.0
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    pos = sum(1 for t in tokens if t in POSITIVE_TERMS)
    neg = sum(1 for t in tokens if t in NEGATIVE_TERMS)
    if pos == 0 and neg == 0:
        return 0.0
    raw = (pos - neg) / math.sqrt(pos + neg)
    # squash into [-1, 1]
    return max(-1.0, min(1.0, raw / 3.0))


def macro_shock_score(items: Iterable[NewsItem]) -> float:
    """Return a 0..1 shock level based on scary macro-news density."""
    hits = 0
    total = 0
    for item in items:
        if not item.is_macro:
            continue
        total += 1
        tokens = set(_tokenize(item.headline + " " + item.summary))
        if tokens & MACRO_SHOCK_TERMS:
            hits += 1
    if total == 0:
        return 0.0
    return min(1.0, hits / max(3, total))


def aggregate_sentiment(items: Iterable[NewsItem], ticker: str) -> float:
    """Average sentiment in [-1, 1] across recent ticker-tagged news."""
    t = ticker.upper()
    scored = [
        score_text(i.headline + " " + i.summary)
        for i in items
        if (i.ticker or "").upper() == t
    ]
    if not scored:
        return 0.0
    return sum(scored) / len(scored)
