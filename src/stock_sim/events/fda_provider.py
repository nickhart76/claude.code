"""FDA PDUFA calendar scraper.

Scrapes the public FDA decision calendar at https://www.drugs.com/fda-calendar.html.
This is a best-effort parser — drugs.com's HTML changes from time to time.
On parse failure the scraper returns an empty list rather than raising, so
`build_calendar` can still return the earnings + macro calendar.

Two ways to use it:

    # Production: fetch live HTML
    events = fetch_fda_calendar()

    # Tests / custom sources: parse a pre-fetched HTML blob
    events = parse_fda_html(html_string, ticker_map={"MODERNA": "MRNA"})

Ticker resolution has two paths:

1. Explicit markup — the scraper looks for ``(NASDAQ:XYZ)`` / ``(NYSE:XYZ)``
   tokens in each row.
2. Name lookup — if a ``ticker_map`` is provided, we match the row text
   against its keys (case-insensitive substring).

Rows that have no ticker after both steps are dropped — the signal engine
only reasons about ticker-scoped events, and a company-less PDUFA date
isn't actionable.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterable, Optional

from .models import Event, EventType

log = logging.getLogger(__name__)


DRUGSCOM_FDA_URL = "https://www.drugs.com/fda-calendar.html"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 stock_sim/0.1"
)


_TICKER_RE = re.compile(r"\((?:NASDAQ|NYSE|AMEX|OTC|OTCMKTS|CBOE)\s*:\s*([A-Z][A-Z.\-]*)\)")
_DATE_PATTERNS = (
    "%b %d, %Y",
    "%B %d, %Y",
    "%b. %d, %Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
)
_LOOSE_DATE_RE = re.compile(
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z.]*\s+\d{1,2},\s*\d{4})"
    r"|(?:\d{4}-\d{2}-\d{2})"
    r"|(?:\d{1,2}/\d{1,2}/\d{4})"
)


def _parse_date(text: str) -> Optional[date]:
    m = _LOOSE_DATE_RE.search(text)
    if not m:
        return None
    token = m.group(0).replace("Sept", "Sep")
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _extract_ticker(text: str, ticker_map: Optional[dict[str, str]]) -> Optional[str]:
    m = _TICKER_RE.search(text)
    if m:
        return m.group(1).upper()
    if ticker_map:
        lowered = text.lower()
        for name, ticker in ticker_map.items():
            if name.lower() in lowered:
                return ticker.upper()
    return None


def parse_fda_html(
    html: str,
    *,
    ticker_map: Optional[dict[str, str]] = None,
) -> list[Event]:
    """Parse drugs.com FDA-calendar HTML into Event objects.

    Defensive: returns ``[]`` if BeautifulSoup is unavailable or the
    markup doesn't match any known pattern.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover
        log.warning("beautifulsoup4 not installed; FDA provider disabled")
        return []

    soup = BeautifulSoup(html, "html.parser")
    seen: set[tuple[str, date, str]] = set()
    out: list[Event] = []

    # Walk any row-ish container and look for (date, ticker) tuples.
    # Using a single generic pass keeps us resilient to class renames.
    candidates: Iterable = soup.find_all(
        ["tr", "li", "article", "div", "p", "section"],
        recursive=True,
    )

    for row in candidates:
        text = row.get_text(" ", strip=True)
        if not text or len(text) < 8 or len(text) > 600:
            continue
        # Must look like an FDA row.
        if not re.search(r"\bPDUFA\b|\bFDA\b|approval|decision", text, re.I):
            continue
        event_date = _parse_date(text)
        if event_date is None:
            continue
        ticker = _extract_ticker(text, ticker_map)
        if ticker is None:
            continue

        description = re.sub(r"\s+", " ", text)[:200]
        key = (ticker, event_date, description[:80])
        if key in seen:
            continue
        seen.add(key)

        out.append(
            Event(
                ticker=ticker,
                event_type=EventType.FDA_DECISION,
                event_date=event_date,
                description=description,
                expected_direction=1,  # FDA approvals are assumed bullish
            )
        )

    return out


def fetch_fda_calendar(
    *,
    url: str = DRUGSCOM_FDA_URL,
    ticker_map: Optional[dict[str, str]] = None,
    timeout: float = 15.0,
) -> list[Event]:
    """Fetch and parse the drugs.com FDA calendar.

    Returns ``[]`` on network or parse failure — failures are logged but
    never raised, so the rest of the event calendar still builds.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover
        log.warning("requests not installed; FDA provider disabled")
        return []

    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
            timeout=timeout,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("FDA calendar fetch failed: %s", exc)
        return []

    return parse_fda_html(response.text, ticker_map=ticker_map)
