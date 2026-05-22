from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_paper: bool
    starting_capital: float
    max_positions: int
    max_position_notional: float
    max_daily_loss_percent: float
    slippage_bps: float
    universe: list[str]
    db_path: Path
    reports_dir: Path

    @property
    def daily_loss_limit_fraction(self) -> float:
        return self.max_daily_loss_percent / 100.0

    @property
    def slippage_fraction(self) -> float:
        return self.slippage_bps / 10_000.0


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _parse_bool(name: str, default: str | None = None) -> bool:
    raw = os.getenv(name, default or "").strip().lower()
    if raw not in {"true", "false"}:
        raise ConfigError(f"{name} must be 'true' or 'false'")
    return raw == "true"


def _parse_float(name: str, default: str) -> float:
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be numeric") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


def _parse_int(name: str, default: str) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


def load_settings() -> Settings:
    load_dotenv()

    universe = [symbol.strip().upper() for symbol in os.getenv("UNIVERSE", "").split(",") if symbol.strip()]
    if not universe:
        raise ConfigError("UNIVERSE must contain at least one symbol")

    settings = Settings(
        alpaca_api_key=_require_env("ALPACA_API_KEY"),
        alpaca_secret_key=_require_env("ALPACA_SECRET_KEY"),
        alpaca_paper=_parse_bool("ALPACA_PAPER"),
        starting_capital=_parse_float("STARTING_CAPITAL", "100"),
        max_positions=_parse_int("MAX_POSITIONS", "3"),
        max_position_notional=_parse_float("MAX_POSITION_NOTIONAL", "30"),
        max_daily_loss_percent=_parse_float("MAX_DAILY_LOSS_PERCENT", "5"),
        slippage_bps=_parse_float("SLIPPAGE_BPS", "10"),
        universe=universe,
        db_path=Path(os.getenv("DB_PATH", "/app/data/trader.db")),
        reports_dir=Path(os.getenv("REPORTS_DIR", "/app/data/reports")),
    )

    if not settings.alpaca_paper:
        raise ConfigError("ALPACA_PAPER must be true. Live trading is not allowed.")

    return settings
