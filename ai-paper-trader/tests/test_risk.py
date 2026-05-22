from pathlib import Path

from bot.config import Settings
from bot.risk import check_buy_risk, estimate_slippage_cost


def build_settings() -> Settings:
    return Settings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpaca_paper=True,
        starting_capital=100.0,
        max_positions=3,
        max_position_notional=30.0,
        max_daily_loss_percent=5.0,
        slippage_bps=10.0,
        universe=["AAPL"],
        db_path=Path("/tmp/test.db"),
        reports_dir=Path("/tmp/reports"),
    )


def test_estimate_slippage_cost() -> None:
    assert estimate_slippage_cost(30.0, 0.001) == 0.03


def test_buy_rejected_when_max_positions_reached() -> None:
    settings = build_settings()
    result = check_buy_risk(
        settings=settings,
        account_buying_power=100.0,
        current_equity=100.0,
        day_start_equity=100.0,
        open_positions=["AAPL", "MSFT", "NVDA"],
        symbol="AMD",
        notional=30.0,
    )
    assert not result.approved
    assert result.reason == "max positions reached"


def test_buy_rejected_when_daily_loss_limit_hit() -> None:
    settings = build_settings()
    result = check_buy_risk(
        settings=settings,
        account_buying_power=100.0,
        current_equity=94.99,
        day_start_equity=100.0,
        open_positions=[],
        symbol="AMD",
        notional=30.0,
    )
    assert not result.approved
    assert result.reason == "daily loss limit reached"


def test_buy_approved_when_all_checks_pass() -> None:
    settings = build_settings()
    result = check_buy_risk(
        settings=settings,
        account_buying_power=100.0,
        current_equity=100.0,
        day_start_equity=100.0,
        open_positions=["AAPL"],
        symbol="AMD",
        notional=20.0,
    )
    assert result.approved
    assert result.reason == "approved"
