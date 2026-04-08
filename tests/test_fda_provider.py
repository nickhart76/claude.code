"""Tests for the FDA PDUFA scraper — no network, hand-written HTML."""

from __future__ import annotations

from datetime import date

import pytest

from stock_sim.events.fda_provider import parse_fda_html
from stock_sim.events.models import EventType


def test_parse_with_ticker_in_parens():
    html = """
    <html><body>
      <table>
        <tr>
          <td>May 15, 2026 - Moderna (NASDAQ:MRNA) - Flu vaccine PDUFA date</td>
        </tr>
        <tr>
          <td>Jun 2, 2026 - Pfizer (NYSE:PFE) - FDA decision on oncology therapy</td>
        </tr>
      </table>
    </body></html>
    """
    events = parse_fda_html(html)
    assert len(events) == 2
    tickers = sorted(e.ticker for e in events)
    assert tickers == ["MRNA", "PFE"]
    assert all(e.event_type == EventType.FDA_DECISION for e in events)
    assert all(e.expected_direction == 1 for e in events)
    mrna = [e for e in events if e.ticker == "MRNA"][0]
    assert mrna.event_date == date(2026, 5, 15)


def test_parse_uses_ticker_map_when_markup_has_no_symbol():
    html = """
    <ul>
      <li>July 12, 2026 — Vertex Pharmaceuticals PDUFA decision on new cystic fibrosis drug</li>
    </ul>
    """
    events = parse_fda_html(html, ticker_map={"Vertex Pharmaceuticals": "VRTX"})
    assert len(events) == 1
    assert events[0].ticker == "VRTX"
    assert events[0].event_date == date(2026, 7, 12)


def test_parse_drops_rows_without_any_resolvable_ticker():
    html = """
    <div>Sep 30, 2026 - SomeBiotech PDUFA decision</div>
    <div>Oct 10, 2026 - Another (NASDAQ:ABCD) - FDA approval decision</div>
    """
    events = parse_fda_html(html)
    assert len(events) == 1
    assert events[0].ticker == "ABCD"


def test_parse_skips_rows_without_dates():
    html = """
    <p>Acme (NASDAQ:ACME) PDUFA sometime next year</p>
    <p>Nov 15, 2026 - Acme (NASDAQ:ACME) PDUFA target action date</p>
    """
    events = parse_fda_html(html)
    assert len(events) == 1
    assert events[0].event_date == date(2026, 11, 15)


def test_parse_skips_rows_without_fda_keywords():
    html = """
    <div>May 1, 2026 - Apple (NASDAQ:AAPL) earnings release</div>
    <div>May 2, 2026 - Moderna (NASDAQ:MRNA) FDA PDUFA decision</div>
    """
    events = parse_fda_html(html)
    assert len(events) == 1
    assert events[0].ticker == "MRNA"


def test_parse_dedupes_repeated_rows():
    # The same row can appear inside both a <tr> and a wrapping <div>.
    html = """
    <table><tr><td>Dec 1, 2026 - Moderna (NASDAQ:MRNA) PDUFA date for vaccine</td></tr></table>
    <div>Dec 1, 2026 - Moderna (NASDAQ:MRNA) PDUFA date for vaccine</div>
    """
    events = parse_fda_html(html)
    assert len(events) == 1


def test_parse_returns_empty_on_unrecognized_markup():
    html = "<html><body><p>Completely unrelated page</p></body></html>"
    assert parse_fda_html(html) == []


def test_parse_handles_various_date_formats():
    html = """
    <ul>
      <li>2026-03-15 - Gilead (NASDAQ:GILD) FDA decision on HIV drug</li>
      <li>April 22, 2026 - Regeneron (NASDAQ:REGN) PDUFA date</li>
      <li>5/30/2026 - Amgen (NASDAQ:AMGN) FDA approval decision</li>
    </ul>
    """
    events = parse_fda_html(html)
    dates = sorted(e.event_date for e in events)
    assert date(2026, 3, 15) in dates
    assert date(2026, 4, 22) in dates
    assert date(2026, 5, 30) in dates
