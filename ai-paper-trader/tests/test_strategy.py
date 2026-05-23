from pathlib import Path

import pandas as pd

from bot.config import Settings
from bot.strategy import filter_candidates, rank_candidates, score_symbol, select_prefilter_candidates


def build_frame(trend: float, volume_boost: float = 0.0, base_volume: float = 1_000_000.0) -> pd.DataFrame:
    closes = [100 + (i * trend) for i in range(25)]
    volumes = [base_volume + (volume_boost if i == 24 else 0.0) for i in range(25)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=25, freq="D"),
            "close": closes,
            "volume": volumes,
        }
    )


def test_score_symbol_returns_candidate_for_sufficient_data() -> None:
    candidate = score_symbol("AAPL", build_frame(1.0, volume_boost=500_000))
    assert candidate is not None
    assert candidate.symbol == "AAPL"
    assert candidate.score > 0
    assert "5d=" in candidate.explanation


def test_score_symbol_returns_none_for_short_history() -> None:
    short_frame = build_frame(1.0).head(10)
    assert score_symbol("AAPL", short_frame) is None


def test_rank_candidates_orders_by_score_descending() -> None:
    frames = {
        "FAST": build_frame(2.0, volume_boost=500_000),
        "SLOW": build_frame(0.5),
    }
    candidates = rank_candidates(frames)
    assert [candidate.symbol for candidate in candidates] == ["FAST", "SLOW"]


def test_select_prefilter_candidates_applies_limit() -> None:
    frames = {
        "FAST": build_frame(2.0, volume_boost=500_000),
        "MID": build_frame(1.0, volume_boost=250_000),
        "SLOW": build_frame(0.5),
    }
    candidates = rank_candidates(frames)
    selected = select_prefilter_candidates(candidates, 2)
    assert [candidate.symbol for candidate in selected] == ["FAST", "MID"]


def test_filter_candidates_enforces_price_and_liquidity_floors() -> None:
    settings = Settings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpaca_paper=True,
        ai_provider="openai",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
        ollama_base_url=None,
        ollama_model="llama3.1",
        ai_research_enabled=False,
        starting_capital=100.0,
        max_positions=3,
        max_position_notional=30.0,
        max_daily_loss_percent=5.0,
        slippage_bps=10.0,
        universe=[],
        research_universe_limit=100,
        ai_research_candidate_count=10,
        min_price=5.0,
        min_avg_dollar_volume=5_000_000.0,
        db_path=Path("/tmp/test.db"),
        reports_dir=Path("/tmp/reports"),
    )
    frames = {
        "LIQUID": build_frame(2.0, volume_boost=500_000),
        "THIN": build_frame(0.1, base_volume=10_000.0),
    }
    candidates = rank_candidates(frames)
    filtered = filter_candidates(candidates, settings)
    assert [candidate.symbol for candidate in filtered] == ["LIQUID"]
