"""CLI entrypoint for the phantom stock event simulator.

Subcommands
-----------
calendar   Show ranked upcoming events with BUY/HOLD/AVOID signals.
news       Dump recent ticker or macro news with sentiment scores.
buy        Place a phantom buy at the latest market close.
sell       Place a phantom sell at the latest market close.
positions  Show open positions and unrealized P&L.
trades     Show trade history.
equity     Show total equity = cash + mark-to-market positions.
reset      Wipe phantom portfolio state and start over.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Iterable

from .config import DEFAULT_CONFIG, DB_PATH
from .events import build_calendar
from .news import build_feed
from .pricing import fetch_history, fetch_last_price
from .portfolio import Portfolio
from .signals import Action, score_events
from .backtest import run_backtest


def _rank_tickers_from_recs(recs) -> list[str]:
    seen = []
    for r in recs:
        if r.event.ticker and r.event.ticker not in seen:
            seen.append(r.event.ticker)
    return seen


def cmd_calendar(args: argparse.Namespace) -> int:
    tickers = _resolve_watchlist(args.tickers)
    print(f"Fetching events + news + prices for {len(tickers)} tickers...")
    cal = build_calendar(tickers)
    feed = build_feed(tickers)
    hist = fetch_history(tickers, period="3mo")
    recs = score_events(cal, feed, hist, config=DEFAULT_CONFIG)

    if not recs:
        print("No upcoming events in horizon.")
        return 0

    horizon = DEFAULT_CONFIG.calendar_horizon_days
    print(f"\nUpcoming events ({horizon}d horizon) — as of {date.today()}\n")
    print(f"{'DATE':<12}{'TICKER':<8}{'ACTION':<8}{'SCORE':>8}  {'EVENT':<28} {'RATIONALE'}")
    print("-" * 110)
    for r in recs:
        tkr = r.event.ticker or "—"
        desc = (r.event.description or r.event.event_type.value)[:26]
        print(
            f"{r.event.event_date.isoformat():<12}"
            f"{tkr:<8}{r.action.value:<8}{r.score:>+8.2f}  {desc:<28} {r.rationale}"
        )
    return 0


def cmd_news(args: argparse.Namespace) -> int:
    tickers = _resolve_watchlist(args.tickers)
    feed = build_feed(tickers)
    if args.macro:
        items = feed.macro(hours=args.hours)
        print(f"\nMacro news (last {args.hours}h):\n")
    else:
        items = feed.recent(hours=args.hours, ticker=args.ticker) if args.ticker else feed.recent(hours=args.hours)
        label = args.ticker or "all watchlist"
        print(f"\nRecent news ({label}, last {args.hours}h):\n")
    from .news.sentiment import score_text

    for item in sorted(items, key=lambda i: i.published_at, reverse=True)[: args.limit]:
        s = score_text(item.headline + " " + item.summary)
        tag = item.ticker or "macro"
        print(f"  [{s:+.2f}] {item.published_at:%Y-%m-%d %H:%M} {tag:<6} {item.source}")
        print(f"         {item.headline}")
    return 0


def cmd_buy(args: argparse.Namespace) -> int:
    price = args.price or fetch_last_price(args.ticker)
    if price is None:
        print(f"could not fetch price for {args.ticker}", file=sys.stderr)
        return 2
    with Portfolio(DB_PATH, starting_cash=DEFAULT_CONFIG.starting_cash) as pf:
        trade = pf.buy(args.ticker, args.quantity, price, note=args.note or "")
        print(
            f"BUY #{trade.id} {trade.quantity:g} {trade.ticker} "
            f"@ ${trade.price:,.2f} (cost ${trade.notional:,.2f})"
        )
        print(f"cash remaining: ${pf.cash:,.2f}")
    return 0


def cmd_sell(args: argparse.Namespace) -> int:
    price = args.price or fetch_last_price(args.ticker)
    if price is None:
        print(f"could not fetch price for {args.ticker}", file=sys.stderr)
        return 2
    with Portfolio(DB_PATH, starting_cash=DEFAULT_CONFIG.starting_cash) as pf:
        trade = pf.sell(args.ticker, args.quantity, price, note=args.note or "")
        print(
            f"SELL #{trade.id} {trade.quantity:g} {trade.ticker} "
            f"@ ${trade.price:,.2f} (proceeds ${trade.notional:,.2f})"
        )
        print(f"cash now: ${pf.cash:,.2f}")
    return 0


def cmd_positions(_: argparse.Namespace) -> int:
    with Portfolio(DB_PATH, starting_cash=DEFAULT_CONFIG.starting_cash) as pf:
        positions = pf.positions()
        if not positions:
            print("no open positions")
            print(f"cash: ${pf.cash:,.2f}")
            return 0
        tickers = [p.ticker for p in positions]
        hist = fetch_history(tickers, period="5d")
        last = {t: hist.last(t) or 0.0 for t in tickers}
        print(f"{'TICKER':<8}{'QTY':>10}{'AVG':>12}{'LAST':>12}{'MKT VAL':>14}{'UNREAL P/L':>14}")
        print("-" * 70)
        for p in positions:
            px = last[p.ticker]
            print(
                f"{p.ticker:<8}{p.quantity:>10.4f}{p.avg_cost:>12,.2f}"
                f"{px:>12,.2f}{p.market_value(px):>14,.2f}{p.unrealized_pl(px):>+14,.2f}"
            )
        equity = pf.equity(last)
        print(f"\ncash:   ${pf.cash:,.2f}")
        print(f"equity: ${equity:,.2f}  (starting ${pf.starting_cash:,.2f}, realized ${pf.realized_pnl_total():+,.2f})")
    return 0


def cmd_trades(_: argparse.Namespace) -> int:
    with Portfolio(DB_PATH, starting_cash=DEFAULT_CONFIG.starting_cash) as pf:
        trades = pf.trades()
        if not trades:
            print("no trades yet")
            return 0
        print(f"{'ID':>4} {'TIME':<20} {'SIDE':<4} {'TICKER':<8}{'QTY':>10}{'PRICE':>12}  NOTE")
        print("-" * 80)
        for t in trades:
            print(
                f"{t.id:>4} {t.timestamp:%Y-%m-%d %H:%M}  {t.side.value:<4} "
                f"{t.ticker:<8}{t.quantity:>10.4f}{t.price:>12,.2f}  {t.note}"
            )
    return 0


def cmd_equity(_: argparse.Namespace) -> int:
    with Portfolio(DB_PATH, starting_cash=DEFAULT_CONFIG.starting_cash) as pf:
        positions = pf.positions()
        tickers = [p.ticker for p in positions]
        last: dict[str, float] = {}
        if tickers:
            hist = fetch_history(tickers, period="5d")
            last = {t: hist.last(t) or 0.0 for t in tickers}
        equity = pf.equity(last)
        delta = equity - pf.starting_cash
        pct = (delta / pf.starting_cash * 100.0) if pf.starting_cash else 0.0
        print(f"cash:      ${pf.cash:,.2f}")
        print(f"equity:    ${equity:,.2f}")
        print(f"starting:  ${pf.starting_cash:,.2f}")
        print(f"P/L:       ${delta:+,.2f}  ({pct:+.2f}%)")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    from datetime import datetime as _dt

    tickers = _resolve_watchlist(args.tickers)
    start = _dt.strptime(args.start, "%Y-%m-%d").date()
    end = _dt.strptime(args.end, "%Y-%m-%d").date()
    print(f"Backtesting {len(tickers)} tickers from {start} to {end}...")
    cal = build_calendar(tickers)
    feed = build_feed(tickers) if not args.no_news else __import__(
        "stock_sim.news", fromlist=["NewsFeed"]
    ).NewsFeed()
    # Pull history covering the whole range + a forward buffer.
    span_days = (end - start).days + args.forward_window + 30
    if span_days <= 60:
        period = "3mo"
    elif span_days <= 180:
        period = "6mo"
    elif span_days <= 365:
        period = "1y"
    elif span_days <= 730:
        period = "2y"
    else:
        period = "5y"
    hist = fetch_history(tickers, period=period)

    result = run_backtest(
        cal,
        hist,
        feed,
        start=start,
        end=end,
        forward_window_days=args.forward_window,
        config=DEFAULT_CONFIG,
    )
    print()
    print(result.summary())
    if args.trades and result.trades:
        print("\ntrades:")
        print(f"{'TICKER':<8}{'ENTRY':<12}{'EXIT':<12}{'RET%':>8}  EVENT")
        for t in result.trades:
            print(
                f"{t.ticker:<8}{t.entry_date.isoformat():<12}"
                f"{t.exit_date.isoformat():<12}{t.return_pct * 100:>+7.2f}  "
                f"{t.event_description}"
            )
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    with Portfolio(DB_PATH, starting_cash=DEFAULT_CONFIG.starting_cash) as pf:
        pf.reset(starting_cash=args.cash)
        print(f"portfolio reset. cash = ${pf.cash:,.2f}")
    return 0


def _resolve_watchlist(explicit: Iterable[str] | None) -> list[str]:
    if explicit:
        return [t.upper() for t in explicit]
    return list(DEFAULT_CONFIG.watchlist)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stocksim", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("calendar", help="ranked upcoming events + recommendations")
    c.add_argument("--tickers", nargs="*", help="override watchlist")
    c.set_defaults(func=cmd_calendar)

    n = sub.add_parser("news", help="recent news with sentiment")
    n.add_argument("--ticker", help="filter to a single ticker")
    n.add_argument("--macro", action="store_true", help="show macro/world news only")
    n.add_argument("--hours", type=int, default=48)
    n.add_argument("--limit", type=int, default=20)
    n.add_argument("--tickers", nargs="*", help="override watchlist")
    n.set_defaults(func=cmd_news)

    b = sub.add_parser("buy", help="place a phantom buy")
    b.add_argument("ticker")
    b.add_argument("quantity", type=float)
    b.add_argument("--price", type=float, help="override fetched price")
    b.add_argument("--note", help="free-form note")
    b.set_defaults(func=cmd_buy)

    s = sub.add_parser("sell", help="place a phantom sell")
    s.add_argument("ticker")
    s.add_argument("quantity", type=float)
    s.add_argument("--price", type=float, help="override fetched price")
    s.add_argument("--note", help="free-form note")
    s.set_defaults(func=cmd_sell)

    sub.add_parser("positions", help="show open positions").set_defaults(func=cmd_positions)
    sub.add_parser("trades", help="show trade history").set_defaults(func=cmd_trades)
    sub.add_parser("equity", help="show total equity").set_defaults(func=cmd_equity)

    r = sub.add_parser("reset", help="wipe portfolio state")
    r.add_argument("--cash", type=float, default=None, help="new starting cash")
    r.set_defaults(func=cmd_reset)

    bt = sub.add_parser("backtest", help="walk-forward backtest of the scoring engine")
    bt.add_argument("--start", required=True, help="YYYY-MM-DD")
    bt.add_argument("--end", required=True, help="YYYY-MM-DD")
    bt.add_argument("--forward-window", type=int, default=5, help="trading days held post-event")
    bt.add_argument("--tickers", nargs="*", help="override watchlist")
    bt.add_argument("--trades", action="store_true", help="print every trade")
    bt.add_argument(
        "--no-news",
        action="store_true",
        help="skip news fetch (use empty feed). Removes look-ahead bias from sentiment.",
    )
    bt.set_defaults(func=cmd_backtest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
