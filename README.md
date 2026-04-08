# stock_sim — phantom-trading event simulator

A small Python project that looks at upcoming scheduled market events
(earnings, FDA decisions, Fed meetings, CPI, jobs report), aggregates
per-ticker and macro news with a lightweight sentiment model, flags stocks
that look "already priced in", and produces a ranked calendar of BUY /
HOLD / AVOID recommendations. All trades are **phantom** — nothing touches
a broker and no money moves.

> **Not financial advice.** This is an educational simulator. Markets are
> efficient enough that toy signal stacks like this one will not reliably
> beat the market. Use it to learn, backtest ideas, and keep yourself
> honest — never as an autotrader.

## What it does

- **Calendar:** fetches real upcoming earnings dates from Yahoo Finance
  (via `yfinance`) for your watchlist, plus a bundled schedule of FOMC
  meetings, CPI releases, and non-farm payrolls.
- **News:** pulls real ticker-level RSS from Yahoo Finance and macro
  news from Yahoo / CNBC / Reuters RSS feeds. No API keys required.
- **Sentiment:** lightweight finance-lexicon scorer (pluggable — swap in
  FinBERT or an LLM behind the same interface).
- **Priced-in detector:** computes recent drift vs. the stock's own
  volatility; if the move has already happened, the signal fades.
- **Macro shock detector:** scans global headlines for war, sanctions,
  shutdowns, rate-hike risk, etc., and applies a drag on all tickers.
- **Scoring engine:** combines the four signals into a score in ~[-1, 1]
  and decides BUY / HOLD / AVOID per event.
- **Phantom portfolio:** SQLite-backed cash + positions, weighted-average
  cost basis, realized and unrealized P&L, full trade log.

## Install

```bash
# from the repo root
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
```

Requires Python 3.10+. Network access is required for live data
(earnings dates, prices, news). There is **no mock-data fallback** —
if your network is down the `calendar`, `news`, `buy`, and `sell`
commands will fail.

## Usage

```bash
# show ranked calendar for the default watchlist
stocksim calendar

# same, but only look at a couple tickers
stocksim calendar --tickers AAPL NVDA MRNA

# recent news for a single ticker
stocksim news --ticker AAPL --hours 48

# only macro / world news
stocksim news --macro --hours 24

# place a phantom buy at the latest close (10 shares of AAPL)
stocksim buy AAPL 10

# or with an explicit price + a note
stocksim buy NVDA 5 --price 880.25 --note "earnings play"

# sell half the position
stocksim sell NVDA 2.5

# see what you hold + unrealized P/L (marks to market via yfinance)
stocksim positions

# trade history and total equity
stocksim trades
stocksim equity

# reset the portfolio with a fresh $100k
stocksim reset --cash 100000
```

## Architecture

```
src/stock_sim/
  config.py            watchlist, scoring weights, thresholds
  events/
    models.py          Event + EventType + baseline impact table
    calendar.py        container with horizon / ticker filters
    providers.py       yfinance earnings + static FOMC/CPI/NFP calendar
  news/
    models.py          NewsItem
    sentiment.py       lexicon sentiment + macro-shock detector
    feed.py            NewsFeed container
    providers.py       Yahoo/CNBC/Reuters RSS via feedparser
  pricing/
    history.py         PriceBar / PriceHistory
    providers.py       yfinance price downloads
    priced_in.py       recent-drift vs. volatility heuristic
  signals/
    engine.py          combines everything into ranked recommendations
  portfolio/
    portfolio.py       SQLite-backed phantom trader
  cli.py               argparse entrypoint
```

Provider imports are lazy, so unit tests and the sentiment/priced-in
logic can run without yfinance / feedparser installed. Live CLI
commands do require them (they come with the base install).

## Tuning signals

All knobs live in `src/stock_sim/config.py`:

- `ScoringWeights` — how much to weight event impact vs. news sentiment
  vs. macro shock vs. priced-in discount.
- `buy_threshold` / `sell_threshold` — decision cutoffs on the final score.
- `calendar_horizon_days` — how far ahead to look.
- `watchlist` — default set of tickers.

The baseline impact per event type lives in
`src/stock_sim/events/models.py` (`DEFAULT_IMPACT`).

## Extending

- **Better sentiment:** replace `news.sentiment.score_text` with a FinBERT
  or LLM classifier. The interface is a single `str -> float in [-1, 1]`.
- **More event types:** add to `EventType` in `events/models.py` and
  populate a provider in `events/providers.py` (FDA PDUFA calendar,
  product launches, Fed speakers, analyst days, etc.).
- **Better priced-in:** swap the drift-vs-vol heuristic for implied-vol
  decomposition or a cross-sectional z-score against the sector.
- **Backtesting:** the portfolio has a trade log with timestamps — replay
  historical prices through `score_events` with `as_of=<past date>` and
  measure hit rate before you trust any live recommendation.

## Tests

```bash
pytest -q
```

The test suite uses in-memory objects only — no network, no fixtures on
disk — so it runs fast and is safe in CI.
