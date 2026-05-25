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


def generate_review_report(settings: Settings) -> Path:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.reports_dir / "paper_trading_review.md"
    with sqlite3.connect(settings.db_path) as conn:
        trades = pd.read_sql_query("SELECT * FROM trades ORDER BY timestamp", conn)
        decisions = pd.read_sql_query("SELECT * FROM decisions ORDER BY timestamp", conn)
        equity = pd.read_sql_query("SELECT * FROM daily_equity ORDER BY timestamp", conn)

    completed = _pair_trade_outcomes(trades)
    losses = [trade for trade in completed if float(trade["pnl"]) <= 0]
    wins = [trade for trade in completed if float(trade["pnl"]) > 0]

    decision_counts = decisions["decision"].value_counts().to_dict() if not decisions.empty else {}
    skip_reason_counts = (
        decisions.loc[decisions["decision"] == "skip", "reason"].value_counts().head(10).to_dict()
        if not decisions.empty
        else {}
    )
    symbol_attention = (
        decisions["symbol"].value_counts().head(10).to_dict()
        if not decisions.empty and "symbol" in decisions
        else {}
    )
    lessons = _derive_lessons(losses, decisions)
    recent_equity = (
        equity[["timestamp", "equity"]].tail(5).to_dict(orient="records")
        if not equity.empty
        else []
    )

    report_lines = [
        "# AI Paper Trader Review",
        "",
        "## Decision Overview",
        f"- Decision counts: {decision_counts or 'No decisions logged'}",
        f"- Top skip reasons: {skip_reason_counts or 'No skip decisions logged'}",
        f"- Most frequently reviewed symbols: {symbol_attention or 'No symbols logged'}",
        f"- Recent equity snapshots: {recent_equity or 'No equity snapshots logged'}",
        "",
        "## Trade Review",
        f"- Closed winning trades: {len(wins)}",
        f"- Closed losing trades: {len(losses)}",
        f"- Worst losses: {_format_trade_list(losses[:5])}",
        "",
        "## Lessons",
    ]

    if lessons:
        report_lines.extend(f"- {lesson}" for lesson in lessons)
    else:
        report_lines.append("- Not enough completed trade history yet to infer recurring mistakes.")

    report_lines.extend(
        [
            "",
            "## Losing Trade Context",
            *_format_loss_context(losses, decisions),
            "",
        ]
    )

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return report_path


def _pair_trade_outcomes(trades: pd.DataFrame) -> list[dict[str, float | str]]:
    if trades.empty:
        return []

    open_buys: dict[str, list[dict[str, float | str]]] = {}
    outcomes: list[dict[str, float | str]] = []
    for row in trades.itertuples(index=False):
        side = str(row.side).lower()
        symbol = str(row.symbol)
        notional = float(row.notional or 0.0)
        estimated_cost = float(row.estimated_cost or 0.0)
        timestamp = str(row.timestamp)

        if side == "buy":
            open_buys.setdefault(symbol, []).append(
                {"notional": notional, "cost": estimated_cost, "timestamp": timestamp}
            )
            continue

        if side == "sell" and open_buys.get(symbol):
            buy = open_buys[symbol].pop(0)
            pnl = notional - buy["notional"] - buy["cost"] - estimated_cost
            outcomes.append(
                {
                    "symbol": symbol,
                    "pnl": pnl,
                    "buy_timestamp": str(buy["timestamp"]),
                    "sell_timestamp": timestamp,
                }
            )

    return outcomes


def _format_trade(trade: dict[str, float | str] | None) -> str:
    if not trade:
        return "N/A"
    return f"{trade['symbol']} (${float(trade['pnl']):.2f})"


def _format_trade_list(trades: list[dict[str, float | str]]) -> str:
    if not trades:
        return "N/A"
    return ", ".join(_format_trade(trade) for trade in trades)


def _derive_lessons(losses: list[dict[str, float | str]], decisions: pd.DataFrame) -> list[str]:
    lessons: list[str] = []
    if decisions.empty:
        return lessons

    skip_reason_counts = decisions.loc[decisions["decision"] == "skip", "reason"].value_counts()
    if not skip_reason_counts.empty:
        top_reason = skip_reason_counts.index[0]
        lessons.append(f"Most common skip reason was '{top_reason}' ({int(skip_reason_counts.iloc[0])} times).")

    if not losses:
        lessons.append("No closed losing trades yet; keep running until there is enough sell history for outcome review.")
        return lessons

    loss_contexts = _loss_context_rows(losses, decisions)
    if not loss_contexts:
        lessons.append("Closed losses exist, but no matching buy-decision context was found in the journal.")
        return lessons

    loss_reasons = pd.Series([row["reason"] for row in loss_contexts if row["reason"]]).value_counts()
    if not loss_reasons.empty:
        lessons.append(
            f"Most common losing-trade research pattern was '{loss_reasons.index[0]}' ({int(loss_reasons.iloc[0])} times)."
        )

    high_vol_losses = 0
    for row in loss_contexts:
        reason = row["reason"]
        if "vol_penalty=" in reason:
            try:
                vol_penalty = float(reason.split("vol_penalty=")[-1].split()[0].split(",")[0])
            except ValueError:
                continue
            if vol_penalty >= 8:
                high_vol_losses += 1
    if high_vol_losses:
        lessons.append(f"{high_vol_losses} losing trades had elevated volatility penalties (>= 8).")

    below_volume_losses = sum("volume_vs_avg20=below" in row["reason"] for row in loss_contexts)
    if below_volume_losses:
        lessons.append(f"{below_volume_losses} losing trades were taken with below-average volume signals.")

    return lessons


def _format_loss_context(losses: list[dict[str, float | str]], decisions: pd.DataFrame) -> list[str]:
    rows = _loss_context_rows(losses, decisions)
    if not rows:
        return ["- No closed losing trades with matching decision context yet."]
    return [
        (
            f"- {row['symbol']} pnl=${row['pnl']:.2f} "
            f"buy_time={row['buy_timestamp']} sell_time={row['sell_timestamp']} "
            f"research={row['reason']}"
        )
        for row in rows[:5]
    ]


def _loss_context_rows(losses: list[dict[str, float | str]], decisions: pd.DataFrame) -> list[dict[str, float | str]]:
    if decisions.empty or not losses:
        return []

    buy_decisions = decisions.loc[decisions["decision"] == "buy", ["timestamp", "symbol", "reason"]].copy()
    if buy_decisions.empty:
        return []

    rows: list[dict[str, float | str]] = []
    for loss in losses:
        symbol = str(loss["symbol"])
        buy_timestamp = str(loss.get("buy_timestamp", ""))
        matched = buy_decisions.loc[
            (buy_decisions["symbol"] == symbol) & (buy_decisions["timestamp"] == buy_timestamp)
        ]
        if matched.empty:
            matched = buy_decisions.loc[buy_decisions["symbol"] == symbol].tail(1)
        if matched.empty:
            continue
        rows.append(
            {
                "symbol": symbol,
                "pnl": float(loss["pnl"]),
                "buy_timestamp": buy_timestamp,
                "sell_timestamp": str(loss.get("sell_timestamp", "")),
                "reason": str(matched.iloc[-1]["reason"]),
            }
        )
    return rows
