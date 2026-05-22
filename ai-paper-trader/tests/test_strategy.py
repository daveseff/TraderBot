import pandas as pd

from bot.strategy import rank_candidates, score_symbol


def build_frame(trend: float, volume_boost: float = 0.0) -> pd.DataFrame:
    closes = [100 + (i * trend) for i in range(25)]
    volumes = [1_000_000 + (volume_boost if i == 24 else 0.0) for i in range(25)]
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
