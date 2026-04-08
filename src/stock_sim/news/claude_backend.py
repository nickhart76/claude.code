"""Anthropic Messages API sentiment backend.

Install with the ``llm`` extra::

    pip install "stock_sim[llm]"

Set ``ANTHROPIC_API_KEY`` in your environment. Optional overrides:

- ``STOCKSIM_CLAUDE_MODEL``   — defaults to ``claude-opus-4-6``
- ``STOCKSIM_CLAUDE_MAX_BATCH`` — defaults to 40 headlines per API call

Design notes
------------
- One API call scores up to ``max_batch`` headlines. For typical watchlist
  feeds (10-50 items / ticker) this is ~1 call per ticker per refresh.
- The system prompt is constant and carries a ``cache_control`` breakpoint,
  so repeated calls inside the 5-minute cache window pay ~0.1x for the
  instructions — the only variable part is the user message.
- Uses `output_config.format` (json_schema with ``strict``) so the response
  is guaranteed to be parseable JSON matching our shape.
- No extended thinking: headline sentiment is a cheap classification task,
  not a reasoning task. Adding adaptive thinking would bloat cost with
  zero accuracy gain.
- Errors bubble up as RuntimeError — we never silently fall back to the
  lexicon, because a silent downgrade masks API configuration bugs.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a financial sentiment analyst.

For each numbered headline the user sends, assign a score from -1.0 to +1.0:
  +1.0 = very bullish for the ticker (record beat, blockbuster, FDA approval, upgrade)
   0.0 = neutral or unrelated to price direction
  -1.0 = very bearish (missed estimates, downgrade, recall, lawsuit, layoffs, FDA rejection)

Weight the headline text, not rumor. Be conservative: reserve |score| > 0.6
for unambiguously directional language. Respond with JSON matching the
provided schema — one entry per input index, in the same order.
""".strip()


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "score": {"type": "number"},
                },
                "required": ["index", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scores"],
    "additionalProperties": False,
}


class ClaudeBackend:
    """Sentiment backend backed by the Anthropic Messages API."""

    name = "claude"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        max_batch: int | None = None,
        client: Any = None,
    ) -> None:
        # Lazy import so `stock_sim` still loads without the `llm` extra.
        if client is None:
            try:
                import anthropic  # noqa: F401
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "ClaudeBackend requires the `llm` extra: "
                    "pip install 'stock_sim[llm]'"
                ) from exc

            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = client

        self.model = model or os.environ.get("STOCKSIM_CLAUDE_MODEL", "claude-opus-4-6")
        self.max_batch = max_batch or int(os.environ.get("STOCKSIM_CLAUDE_MAX_BATCH", "40"))

    # ---- public scoring API ---------------------------------------

    def score(self, text: str) -> float:
        if not text.strip():
            return 0.0
        return self.score_batch([text])[0]

    def score_batch(self, texts: list[str]) -> list[float]:
        if not texts:
            return []
        out: list[float] = []
        for i in range(0, len(texts), self.max_batch):
            chunk = texts[i : i + self.max_batch]
            out.extend(self._score_chunk(chunk))
        return out

    # ---- internals ------------------------------------------------

    def _score_chunk(self, texts: list[str]) -> list[float]:
        prompt_lines = [
            f"{i}. {t.strip() or '(empty)'}" for i, t in enumerate(texts)
        ]
        user_msg = (
            "Score each of the following headlines. Respond with a JSON "
            "object {\"scores\": [{\"index\": i, \"score\": s}, ...]} "
            f"containing exactly {len(texts)} entries in order.\n\n"
            + "\n".join(prompt_lines)
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": _OUTPUT_SCHEMA,
                    }
                },
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Claude sentiment call failed: {exc}") from exc

        text_block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
        if text_block is None:
            raise RuntimeError("Claude sentiment response had no text block")
        try:
            payload = json.loads(text_block.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Claude sentiment response was not JSON: {exc}") from exc

        scores_out = [0.0] * len(texts)
        for entry in payload.get("scores", []):
            idx = int(entry.get("index", -1))
            if 0 <= idx < len(texts):
                raw = float(entry.get("score", 0.0))
                scores_out[idx] = max(-1.0, min(1.0, raw))
        return scores_out
