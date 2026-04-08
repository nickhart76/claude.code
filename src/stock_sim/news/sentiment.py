"""Sentiment scoring.

Two backends live behind a common interface:

- `LexiconBackend`  — dependency-free word-list scorer. Default.
- `ClaudeBackend`   — calls the Anthropic Messages API with a structured
                      JSON schema. Requires the `llm` extra and
                      ``ANTHROPIC_API_KEY``. See `claude_backend.py`.

Select a backend explicitly with ``set_backend(...)`` or via the
``STOCKSIM_SENTIMENT_BACKEND`` env var (``lexicon`` or ``claude``).

`macro_shock_score` keeps its own word-match logic — it's a quick
O(n) scan of macro headlines, not per-headline sentiment.
"""

from __future__ import annotations

import math
import os
import re
from typing import Iterable, Protocol

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

MACRO_SHOCK_TERMS = {
    "war", "invasion", "strike", "attack", "pandemic", "recession",
    "crash", "default", "shutdown", "rate-hike", "rate-hikes",
}


_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ---- backends -------------------------------------------------------


class SentimentBackend(Protocol):
    """Score headlines on a -1..+1 scale."""

    def score(self, text: str) -> float: ...
    def score_batch(self, texts: list[str]) -> list[float]: ...


def _lexicon_score(text: str) -> float:
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
    return max(-1.0, min(1.0, raw / 3.0))


class LexiconBackend:
    """Zero-dependency lexicon scorer. Fast, dumb, always-available."""

    name = "lexicon"

    def score(self, text: str) -> float:
        return _lexicon_score(text)

    def score_batch(self, texts: list[str]) -> list[float]:
        return [_lexicon_score(t) for t in texts]


_backend: SentimentBackend | None = None


def set_backend(backend: SentimentBackend) -> None:
    """Inject a specific backend. Primarily useful in tests and CLI overrides."""
    global _backend
    _backend = backend


def reset_backend() -> None:
    """Forget any previously set backend (next call will re-resolve)."""
    global _backend
    _backend = None


def get_backend() -> SentimentBackend:
    """Resolve the active backend — env var, then default to lexicon."""
    global _backend
    if _backend is not None:
        return _backend
    name = os.environ.get("STOCKSIM_SENTIMENT_BACKEND", "lexicon").strip().lower()
    if name == "claude":
        from .claude_backend import ClaudeBackend

        _backend = ClaudeBackend()
    else:
        _backend = LexiconBackend()
    return _backend


# ---- public API used by the rest of the package --------------------


def score_text(text: str) -> float:
    """Return a sentiment score in [-1, 1] for a blob of text."""
    return get_backend().score(text)


def macro_shock_score(items: Iterable[NewsItem]) -> float:
    """0..1 shock level based on scary macro-news density.

    Always uses the lexicon — this is a binary keyword search, not
    per-headline sentiment analysis.
    """
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
    """Average sentiment in [-1, 1] across recent ticker-tagged news.

    Uses the active backend's `score_batch` so Claude-backed scoring can
    issue a single API call for all headlines instead of N calls.
    """
    t = ticker.upper()
    texts = [
        i.headline + " " + i.summary
        for i in items
        if (i.ticker or "").upper() == t
    ]
    if not texts:
        return 0.0
    scores = get_backend().score_batch(texts)
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
