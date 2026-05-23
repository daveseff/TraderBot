from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import Settings


@dataclass(frozen=True)
class Candidate:
    symbol: str
    score: float
    explanation: str
    price: float
    momentum_5d: float
    momentum_20d: float
    volatility: float
    avg_dollar_volume_20d: float


def _pct_change(current: float, prior: float) -> float:
    if prior == 0:
        return 0.0
    return (current / prior) - 1.0


def score_symbol(symbol: str, frame: pd.DataFrame) -> Candidate | None:
    if frame.empty or len(frame) < 21:
        return None

    data = frame.sort_values("timestamp").reset_index(drop=True).copy()
    data["sma_20"] = data["close"].rolling(20).mean()
    data["vol_avg_20"] = data["volume"].rolling(20).mean()
    data["returns"] = data["close"].pct_change()

    latest = data.iloc[-1]
    prior_5 = data.iloc[-6]
    prior_20 = data.iloc[-21]

    momentum_5d = _pct_change(float(latest["close"]), float(prior_5["close"]))
    momentum_20d = _pct_change(float(latest["close"]), float(prior_20["close"]))
    price_above_sma = 1.0 if float(latest["close"]) > float(latest["sma_20"]) else -1.0
    volume_above_avg = 1.0 if float(latest["volume"]) > float(latest["vol_avg_20"]) else -1.0
    volatility = float(data["returns"].tail(20).std(ddof=0) or 0.0)
    volatility_penalty = volatility * 100.0

    score = (momentum_5d * 100.0) + (momentum_20d * 100.0) + price_above_sma + volume_above_avg - volatility_penalty
    explanation = (
        f"5d={momentum_5d:.2%}, 20d={momentum_20d:.2%}, "
        f"price_vs_sma20={'above' if price_above_sma > 0 else 'below'}, "
        f"volume_vs_avg20={'above' if volume_above_avg > 0 else 'below'}, "
        f"vol_penalty={volatility_penalty:.2f}"
    )

    return Candidate(
        symbol=symbol,
        score=round(score, 4),
        explanation=explanation,
        price=float(latest["close"]),
        momentum_5d=momentum_5d,
        momentum_20d=momentum_20d,
        volatility=volatility,
        avg_dollar_volume_20d=float((data["close"] * data["volume"]).tail(20).mean()),
    )


def rank_candidates(frames: dict[str, pd.DataFrame]) -> list[Candidate]:
    candidates = [candidate for symbol, frame in frames.items() if (candidate := score_symbol(symbol, frame))]
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def select_prefilter_candidates(candidates: list[Candidate], limit: int) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda candidate: (candidate.score, candidate.avg_dollar_volume_20d),
        reverse=True,
    )[:limit]


def filter_candidates(candidates: list[Candidate], settings: Settings) -> list[Candidate]:
    return [
        candidate
        for candidate in candidates
        if candidate.price >= settings.min_price and candidate.avg_dollar_volume_20d >= settings.min_avg_dollar_volume
    ]
