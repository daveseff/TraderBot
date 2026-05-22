from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class RiskResult:
    approved: bool
    reason: str
    estimated_cost: float


def estimate_slippage_cost(notional: float, slippage_fraction: float) -> float:
    return round(notional * slippage_fraction, 4)


def check_buy_risk(
    *,
    settings: Settings,
    account_buying_power: float,
    current_equity: float,
    day_start_equity: float,
    open_positions: list[str],
    symbol: str,
    notional: float,
) -> RiskResult:
    estimated_cost = estimate_slippage_cost(notional, settings.slippage_fraction)

    if not settings.alpaca_paper:
        return RiskResult(False, "paper trading disabled", estimated_cost)
    if notional > settings.max_position_notional:
        return RiskResult(False, "notional exceeds max position size", estimated_cost)
    if len(open_positions) >= settings.max_positions:
        return RiskResult(False, "max positions reached", estimated_cost)
    if symbol in open_positions:
        return RiskResult(False, "symbol already held", estimated_cost)
    if account_buying_power < notional + estimated_cost:
        return RiskResult(False, "insufficient buying power", estimated_cost)
    if current_equity <= day_start_equity * (1 - settings.daily_loss_limit_fraction):
        return RiskResult(False, "daily loss limit reached", estimated_cost)
    return RiskResult(True, "approved", estimated_cost)
