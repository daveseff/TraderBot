from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
from dataclasses import replace

from .ai_research import AIResearcher
from .broker_alpaca import AlpacaPaperBroker
from .config import Settings, load_settings
from .journal import DecisionLog, Journal
from .market_data import MarketDataService
from .report import generate_report, generate_review_report
from .risk import check_buy_risk, estimate_slippage_cost
from .strategy import Candidate, filter_candidates, rank_candidates, select_prefilter_candidates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def run_scan(settings: Settings, broker: AlpacaPaperBroker, journal: Journal) -> None:
    symbols = _resolve_universe(settings, broker)
    market_data = MarketDataService(settings)
    frames = market_data.get_recent_bars(symbols)
    scored_candidates = rank_candidates(frames)
    candidates = filter_candidates(scored_candidates, settings)
    candidates = _apply_research_layer(settings, candidates)
    _log_research_summary(
        mode="scan",
        universe_count=len(symbols),
        scored_count=len(scored_candidates),
        filtered_count=len(candidates),
        candidates=candidates,
    )
    ranked_symbols = {candidate.symbol for candidate in candidates}
    for symbol, frame in frames.items():
        if symbol in ranked_symbols:
            continue
        reason = "no market data available" if frame.empty else "insufficient price history for scoring"
        journal.log_decision(
            DecisionLog(
                symbol=symbol,
                score=None,
                decision="skip",
                reason=reason,
                notional=None,
                estimated_cost=None,
                order_id=None,
            )
        )
    if not candidates:
        LOGGER.info("No candidates produced from current data.")
        return
    for candidate in candidates:
        journal.log_decision(
            DecisionLog(
                symbol=candidate.symbol,
                score=candidate.score,
                decision="scan",
                reason=candidate.explanation,
                notional=None,
                estimated_cost=None,
                order_id=None,
            )
        )
        LOGGER.info("SCAN %s score=%.2f %s", candidate.symbol, candidate.score, _brief(candidate.explanation))


def run_trade(settings: Settings, broker: AlpacaPaperBroker, journal: Journal) -> None:
    account = broker.get_account()
    account_cash_limit = _get_cash_only_buying_power(account)
    if account_cash_limit <= 0:
        raise RuntimeError("No cash buying power available for paper trading.")

    if getattr(account, "multiplier", None):
        LOGGER.info(
            "Account multiplier=%s detected; enforcing no-margin mode with cash-only buying power %.2f.",
            account.multiplier,
            account_cash_limit,
        )

    positions = broker.get_positions()
    held_symbols = [position.symbol for position in positions]
    bought_symbols: list[str] = []
    sold_symbols: list[str] = []
    _log_positions_snapshot("START", positions)
    journal.log_daily_equity(
        equity=float(account.equity),
        cash=float(account.cash),
        buying_power=float(account.buying_power),
    )

    market_data = MarketDataService(settings)
    symbols = _resolve_universe(settings, broker)
    frames = market_data.get_recent_bars(symbols)
    scored_candidates = rank_candidates(frames)
    candidates = filter_candidates(scored_candidates, settings)
    candidates = _apply_research_layer(settings, candidates)
    _log_research_summary(
        mode="trade",
        universe_count=len(symbols),
        scored_count=len(scored_candidates),
        filtered_count=len(candidates),
        candidates=candidates,
    )
    ranked_symbols = {candidate.symbol for candidate in candidates}
    for symbol, frame in frames.items():
        if symbol in ranked_symbols:
            continue
        reason = "no market data available" if frame.empty else "insufficient price history for scoring"
        journal.log_decision(
            DecisionLog(
                symbol=symbol,
                score=None,
                decision="skip",
                reason=reason,
                notional=None,
                estimated_cost=None,
                order_id=None,
            )
        )
    if not candidates:
        LOGGER.info("No trade candidates available.")
        return

    available_slots = max(settings.max_positions - len(held_symbols), 0)
    day_start_equity = journal.get_day_start_equity() or settings.starting_capital
    for candidate in candidates[:available_slots]:
        risk = check_buy_risk(
            settings=settings,
            account_buying_power=account_cash_limit,
            current_equity=float(account.equity),
            day_start_equity=day_start_equity,
            open_positions=held_symbols,
            symbol=candidate.symbol,
            notional=settings.max_position_notional,
        )
        if not risk.approved:
            journal.log_decision(
                DecisionLog(
                    symbol=candidate.symbol,
                    score=candidate.score,
                    decision="skip",
                    reason=risk.reason,
                    notional=settings.max_position_notional,
                    estimated_cost=risk.estimated_cost,
                    order_id=None,
                )
            )
            LOGGER.info(
                "DECISION SKIP %s score=%.2f reason=%s research=%s",
                candidate.symbol,
                candidate.score,
                risk.reason,
                _brief(candidate.explanation),
            )
            continue

        order = broker.submit_market_buy_notional(candidate.symbol, settings.max_position_notional)
        held_symbols.append(candidate.symbol)
        journal.log_decision(
            DecisionLog(
                symbol=candidate.symbol,
                score=candidate.score,
                decision="buy",
                reason=candidate.explanation,
                notional=settings.max_position_notional,
                estimated_cost=risk.estimated_cost,
                order_id=str(order.id),
            )
        )
        journal.log_trade(
            symbol=candidate.symbol,
            side="buy",
            qty=None,
            notional=settings.max_position_notional,
            estimated_cost=risk.estimated_cost,
            order_id=str(order.id),
            status=getattr(order, "status", None),
        )
        LOGGER.info(
            "DECISION BUY %s score=%.2f notional=%.2f cost=%.4f thesis=%s",
            candidate.symbol,
            candidate.score,
            settings.max_position_notional,
            risk.estimated_cost,
            _brief(candidate.explanation),
        )
        bought_symbols.append(candidate.symbol)

    for candidate in candidates[available_slots:]:
        journal.log_decision(
            DecisionLog(
                symbol=candidate.symbol,
                score=candidate.score,
                decision="skip",
                reason="no remaining position slots",
                notional=settings.max_position_notional,
                estimated_cost=estimate_slippage_cost(settings.max_position_notional, settings.slippage_fraction),
                order_id=None,
            )
        )
        LOGGER.info(
            "DECISION SKIP %s score=%.2f reason=no remaining position slots research=%s",
            candidate.symbol,
            candidate.score,
            _brief(candidate.explanation),
        )

    end_positions = broker.get_positions()
    _log_cycle_activity(bought_symbols=bought_symbols, sold_symbols=sold_symbols)
    _log_positions_snapshot("END", end_positions)


def run_close_all(settings: Settings, broker: AlpacaPaperBroker, journal: Journal) -> None:
    positions = broker.get_positions()
    sold_symbols: list[str] = []
    _log_positions_snapshot("PRE-CLOSE", positions)
    for position in positions:
        qty = float(position.qty)
        notional = float(position.market_value)
        estimated_cost = estimate_slippage_cost(notional, settings.slippage_fraction)
        order = broker.submit_market_sell_qty(position.symbol, qty)
        journal.log_decision(
            DecisionLog(
                symbol=position.symbol,
                score=None,
                decision="sell",
                reason="close-all command",
                notional=notional,
                estimated_cost=estimated_cost,
                order_id=str(order.id),
            )
        )
        journal.log_trade(
            symbol=position.symbol,
            side="sell",
            qty=qty,
            notional=notional,
            estimated_cost=estimated_cost,
            order_id=str(order.id),
            status=getattr(order, "status", None),
        )
        LOGGER.info("Submitted sell for %s qty=%s", position.symbol, position.qty)
        sold_symbols.append(position.symbol)
    _log_cycle_activity(bought_symbols=[], sold_symbols=sold_symbols)


def run_report(settings: Settings) -> None:
    path = generate_report(settings)
    LOGGER.info("Report written to %s", path)


def run_review(settings: Settings) -> None:
    path = generate_review_report(settings)
    LOGGER.info("Review report written to %s", path)


def run_daemon(settings: Settings, broker: AlpacaPaperBroker, journal: Journal) -> None:
    LOGGER.info(
        "Starting continuous trader loop with interval=%ss market_open_only=%s",
        settings.run_interval_seconds,
        settings.market_open_only,
    )
    cycle = 0
    while True:
        cycle += 1
        try:
            if settings.market_open_only:
                clock = broker.get_clock()
                if not getattr(clock, "is_open", False):
                    sleep_seconds = _seconds_until_next_open(getattr(clock, "next_open", None))
                    LOGGER.info(
                        "Cycle %d skipped: market closed. Next open=%s next close=%s sleep_seconds=%s",
                        cycle,
                        getattr(clock, "next_open", None),
                        getattr(clock, "next_close", None),
                        sleep_seconds,
                    )
                    time.sleep(sleep_seconds)
                    continue

            LOGGER.info("Starting trading cycle %d", cycle)
            run_trade(settings, broker, journal)
            LOGGER.info("Completed trading cycle %d", cycle)
        except KeyboardInterrupt:
            LOGGER.info("Trader loop interrupted; exiting.")
            raise
        except Exception:
            LOGGER.exception("Trading cycle %d failed; continuing after sleep.", cycle)

        time.sleep(settings.run_interval_seconds)


def _get_cash_only_buying_power(account) -> float:
    values: list[float] = []
    for field_name in ("cash", "non_marginable_buying_power", "buying_power"):
        raw_value = getattr(account, field_name, None)
        if raw_value is None:
            continue
        try:
            values.append(float(raw_value))
        except (TypeError, ValueError):
            continue
    positive_values = [value for value in values if value > 0]
    return min(positive_values) if positive_values else 0.0


def _seconds_until_next_open(next_open: object) -> int:
    if not isinstance(next_open, datetime):
        return 3600
    now = datetime.now(timezone.utc)
    delta = (next_open - now).total_seconds()
    return max(int(delta) + 5, 60)


def _log_research_summary(
    *,
    mode: str,
    universe_count: int,
    scored_count: int,
    filtered_count: int,
    candidates: list[Candidate],
) -> None:
    LOGGER.info(
        "RESEARCH mode=%s universe=%d scored=%d ranked=%d",
        mode,
        universe_count,
        scored_count,
        filtered_count,
    )
    for index, candidate in enumerate(candidates[:5], start=1):
        LOGGER.info(
            "RANK %d %s score=%.2f price=%.2f adv20=$%.0f why=%s",
            index,
            candidate.symbol,
            candidate.score,
            candidate.price,
            candidate.avg_dollar_volume_20d,
            _brief(candidate.explanation),
        )


def _log_positions_snapshot(label: str, positions: list) -> None:
    if not positions:
        LOGGER.info("POSITIONS %s none", label)
        return

    summary = ", ".join(
        f"{position.symbol}(qty={float(position.qty):.6f}, mv=${float(position.market_value):.2f})"
        for position in positions
    )
    LOGGER.info("POSITIONS %s count=%d %s", label, len(positions), summary)


def _log_cycle_activity(*, bought_symbols: list[str], sold_symbols: list[str]) -> None:
    bought = ", ".join(bought_symbols) if bought_symbols else "none"
    sold = ", ".join(sold_symbols) if sold_symbols else "none"
    LOGGER.info("CYCLE ACTIVITY bought=%s sold=%s", bought, sold)


def _brief(reason: str, limit: int = 220) -> str:
    compact = " ".join(reason.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _resolve_universe(settings: Settings, broker: AlpacaPaperBroker) -> list[str]:
    if settings.universe:
        return settings.universe
    symbols = broker.list_tradable_symbols(settings.research_universe_limit)
    if not symbols:
        raise RuntimeError("No tradable symbols discovered from Alpaca.")
    LOGGER.info("Discovered %d tradable symbols from Alpaca for research.", len(symbols))
    return symbols


def _apply_research_layer(settings: Settings, candidates: list[Candidate]) -> list[Candidate]:
    prefiltered = select_prefilter_candidates(candidates, settings.ai_research_candidate_count)
    researcher = AIResearcher(settings)
    if not researcher.enabled:
        LOGGER.info(
            "AI research disabled or no OPENAI_API_KEY set; using rule-based ranking across %d prefiltered symbols.",
            len(prefiltered),
        )
        return prefiltered

    ai_decisions = researcher.rank_candidates(prefiltered)
    if not ai_decisions:
        LOGGER.info("AI research returned no ranking; using rule-based ranking.")
        return prefiltered

    by_symbol = {candidate.symbol: candidate for candidate in prefiltered}
    ranked: list[Candidate] = []
    for decision in sorted(ai_decisions, key=lambda item: item.ai_rank):
        candidate = by_symbol.get(decision.symbol)
        if candidate is None:
            continue
        ranked.append(
            replace(
                candidate,
                score=decision.ai_score,
                explanation=f"AI thesis: {decision.thesis} | Risks: {decision.risks} | Base: {candidate.explanation}",
            )
        )

    remaining = [candidate for candidate in prefiltered if candidate.symbol not in {item.symbol for item in ranked}]
    return ranked + remaining


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper-only Alpaca trading bot")
    parser.add_argument("mode", choices=["scan", "trade", "daemon", "close-all", "report", "review"])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = load_settings()
    journal = Journal(settings.db_path)

    if args.mode == "report":
        run_report(settings)
        return
    if args.mode == "review":
        run_review(settings)
        return

    broker = AlpacaPaperBroker(settings)

    if args.mode == "scan":
        run_scan(settings, broker, journal)
    elif args.mode == "trade":
        run_trade(settings, broker, journal)
    elif args.mode == "daemon":
        run_daemon(settings, broker, journal)
    elif args.mode == "close-all":
        run_close_all(settings, broker, journal)


if __name__ == "__main__":
    main()
