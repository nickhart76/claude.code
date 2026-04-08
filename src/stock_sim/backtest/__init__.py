"""Backtesting: rerun the scoring engine with `as_of=<past date>` and
measure forward returns on its BUY recommendations."""

from .runner import BacktestResult, BacktestTrade, run_backtest

__all__ = ["BacktestResult", "BacktestTrade", "run_backtest"]
