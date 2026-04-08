"""Tests for the Claude sentiment backend.

Uses a fake Anthropic client — no network, no API key, no `anthropic`
package required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from stock_sim.news import sentiment
from stock_sim.news.claude_backend import ClaudeBackend
from stock_sim.news.feed import NewsFeed
from stock_sim.news.models import NewsItem
from stock_sim.news.sentiment import (
    aggregate_sentiment,
    get_backend,
    reset_backend,
    score_text,
    set_backend,
)


@dataclass
class _FakeTextBlock:
    type: str
    text: str


@dataclass
class _FakeResponse:
    content: list


class _FakeMessages:
    def __init__(self, script: list[list[float]]):
        # `script` is a list of response rows — each row is the scores to
        # return for the Nth call, in index order.
        self._script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        scores = self._script.pop(0) if self._script else []
        payload = {"scores": [{"index": i, "score": float(s)} for i, s in enumerate(scores)]}
        return _FakeResponse(content=[_FakeTextBlock(type="text", text=json.dumps(payload))])


class _FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


@pytest.fixture(autouse=True)
def _clean_backend():
    reset_backend()
    yield
    reset_backend()


def test_claude_backend_scores_headlines_from_response():
    client = _FakeClient([[0.8, -0.6, 0.1]])
    backend = ClaudeBackend(client=client, model="claude-opus-4-6", max_batch=10)
    scores = backend.score_batch(["Apple beats", "Pfizer crashes", "A quiet day"])
    assert scores == [0.8, -0.6, 0.1]
    # one API call
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    # Cache breakpoint on the system prompt.
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Structured output requested.
    assert call["output_config"]["format"]["type"] == "json_schema"
    # Opus 4.6 per skill guidance.
    assert call["model"] == "claude-opus-4-6"


def test_claude_backend_clamps_to_pm_one():
    client = _FakeClient([[5.0, -17.0, 0.0]])
    backend = ClaudeBackend(client=client)
    assert backend.score_batch(["a", "b", "c"]) == [1.0, -1.0, 0.0]


def test_claude_backend_chunks_over_max_batch():
    # 3 items, max_batch=2 -> two API calls (2 + 1).
    client = _FakeClient([[0.4, 0.5], [-0.3]])
    backend = ClaudeBackend(client=client, max_batch=2)
    scores = backend.score_batch(["h1", "h2", "h3"])
    assert scores == [0.4, 0.5, -0.3]
    assert len(client.messages.calls) == 2


def test_claude_backend_single_score_delegates_to_batch():
    client = _FakeClient([[0.42]])
    backend = ClaudeBackend(client=client)
    assert backend.score("Apple beats earnings") == 0.42


def test_claude_backend_raises_on_invalid_json():
    client = _FakeClient([])
    # Push a malformed response by overriding the messages client.
    class _BrokenMessages:
        def create(self, **_):
            return _FakeResponse(content=[_FakeTextBlock(type="text", text="{not json")])

    client.messages = _BrokenMessages()
    backend = ClaudeBackend(client=client)
    with pytest.raises(RuntimeError, match="not JSON"):
        backend.score_batch(["something"])


def test_set_backend_routes_score_text_through_claude():
    client = _FakeClient([[0.9]])
    set_backend(ClaudeBackend(client=client))
    assert score_text("Apple beats earnings in blockbuster quarter") == 0.9


def test_aggregate_sentiment_uses_batch_when_backend_set():
    client = _FakeClient([[0.6, 0.8]])
    set_backend(ClaudeBackend(client=client))

    feed = NewsFeed()
    now = datetime.now(timezone.utc)
    feed.add(NewsItem("Apple beats estimates", now, "r", "AAPL"))
    feed.add(NewsItem("Apple analyst upgrade", now, "r", "AAPL"))

    avg = aggregate_sentiment(feed.items, "AAPL")
    assert avg == pytest.approx(0.7)
    # Only one API call for two headlines (batched).
    assert len(client.messages.calls) == 1


def test_env_var_selects_backend(monkeypatch):
    monkeypatch.setenv("STOCKSIM_SENTIMENT_BACKEND", "lexicon")
    reset_backend()
    assert get_backend().__class__.__name__ == "LexiconBackend"

    monkeypatch.setenv("STOCKSIM_SENTIMENT_BACKEND", "unknown-thing")
    reset_backend()
    # unknown -> default to lexicon
    assert get_backend().__class__.__name__ == "LexiconBackend"
