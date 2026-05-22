from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import Settings


def generate_report(settings: Settings) -> Path:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.reports_dir / "paper_trading_report.md"
    with sqlite3.connect(settings.db_path) as conn:
        trades = pd.read_sql_query("SELECT * FROM trades ORDER BY timestamp", conn)
        decisions = pd.read_sql_query("SELECT * FROM decisions ORDER BY timestamp", conn)
        equity = pd.read_sql_query("SELECT * FROM daily_equity ORDER BY timestamp", conn)

    starting_capital = settings.starting_capital
    ending_equity = float(equity["equity"].iloc[-1]) if not equity.empty else starting_capital
    pnl_dollars = ending_equity - starting_capital
    pnl_percent = (pnl_dollars / starting_capital) * 100.0 if starting_capital else 0.0
    trade_count = len(trades)
    estimated_costs = float(trades["estimated_cost"].sum()) if not trades.empty else 0.0
    open_positions = trades[trades["side"].str.lower() == "buy"]["symbol"].nunique() - trades[trades["side"].str.lower() == "sell"]["symbol"].nunique() if not trades.empty else 0

    completed = _pair_trade_outcomes(trades)
    wins = sum(1 for trade in completed if trade["pnl"] > 0)
    losses = sum(1 for trade in completed if trade["pnl"] <= 0)
    best_trade = max(completed, key=lambda item: item["pnl"], default=None)
    worst_trade = min(completed, key=lambda item: item["pnl"], default=None)

    decision_summary = decisions["decision"].value_counts().to_dict() if not decisions.empty else {}

    report = "\n".join(
        [
            "# AI Paper Trader Report",
            "",
            f"- Starting capital: ${starting_capital:.2f}",
            f"- Ending equity: ${ending_equity:.2f}",
            f"- P/L dollars: ${pnl_dollars:.2f}",
            f"- P/L percent: {pnl_percent:.2f}%",
            f"- Trades made: {trade_count}",
            f"- Win/loss count: {wins}/{losses}",
            f"- Open positions: {open_positions}",
            f"- Estimated costs: ${estimated_costs:.2f}",
            f"- Best trade: {_format_trade(best_trade)}",
            f"- Worst trade: {_format_trade(worst_trade)}",
            f"- Decision log summary: {decision_summary or 'No decisions logged'}",
            "",
        ]
    )
    report_path.write_text(report, encoding="utf-8")
    return report_path


def _pair_trade_outcomes(trades: pd.DataFrame) -> list[dict[str, float | str]]:
    if trades.empty:
        return []

    open_buys: dict[str, list[dict[str, float]]] = {}
    outcomes: list[dict[str, float | str]] = []
    for row in trades.itertuples(index=False):
        side = str(row.side).lower()
        symbol = str(row.symbol)
        notional = float(row.notional or 0.0)
        estimated_cost = float(row.estimated_cost or 0.0)

        if side == "buy":
            open_buys.setdefault(symbol, []).append({"notional": notional, "cost": estimated_cost})
            continue

        if side == "sell" and open_buys.get(symbol):
            buy = open_buys[symbol].pop(0)
            pnl = notional - buy["notional"] - buy["cost"] - estimated_cost
            outcomes.append({"symbol": symbol, "pnl": pnl})

    return outcomes


def _format_trade(trade: dict[str, float | str] | None) -> str:
    if not trade:
        return "N/A"
    return f"{trade['symbol']} (${float(trade['pnl']):.2f})"
