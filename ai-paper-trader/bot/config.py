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
    ai_provider: str
    openai_api_key: str | None
    openai_model: str
    ollama_base_url: str | None
    ollama_model: str
    ai_research_enabled: bool
    starting_capital: float
    max_positions: int
    max_position_notional: float
    max_daily_loss_percent: float
    slippage_bps: float
    universe: list[str]
    research_universe_limit: int
    ai_research_candidate_count: int
    min_price: float
    min_avg_dollar_volume: float
    run_interval_seconds: int
    market_open_only: bool
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

    settings = Settings(
        alpaca_api_key=_require_env("ALPACA_API_KEY"),
        alpaca_secret_key=_require_env("ALPACA_SECRET_KEY"),
        alpaca_paper=_parse_bool("ALPACA_PAPER"),
        ai_provider=os.getenv("AI_PROVIDER", "openai").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "").strip() or None,
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1").strip(),
        ai_research_enabled=_parse_bool("AI_RESEARCH_ENABLED", "true"),
        starting_capital=_parse_float("STARTING_CAPITAL", "100"),
        max_positions=_parse_int("MAX_POSITIONS", "3"),
        max_position_notional=_parse_float("MAX_POSITION_NOTIONAL", "30"),
        max_daily_loss_percent=_parse_float("MAX_DAILY_LOSS_PERCENT", "5"),
        slippage_bps=_parse_float("SLIPPAGE_BPS", "10"),
        universe=universe,
        research_universe_limit=_parse_int("RESEARCH_UNIVERSE_LIMIT", "200"),
        ai_research_candidate_count=_parse_int("AI_RESEARCH_CANDIDATE_COUNT", "12"),
        min_price=_parse_float("MIN_PRICE", "5"),
        min_avg_dollar_volume=_parse_float("MIN_AVG_DOLLAR_VOLUME", "5000000"),
        run_interval_seconds=_parse_int("RUN_INTERVAL_SECONDS", "900"),
        market_open_only=_parse_bool("MARKET_OPEN_ONLY", "true"),
        db_path=Path(os.getenv("DB_PATH", "/app/data/trader.db")),
        reports_dir=Path(os.getenv("REPORTS_DIR", "/app/data/reports")),
    )

    if not settings.alpaca_paper:
        raise ConfigError("ALPACA_PAPER must be true. Live trading is not allowed.")
    if settings.ai_research_candidate_count > settings.research_universe_limit:
        raise ConfigError("AI_RESEARCH_CANDIDATE_COUNT cannot exceed RESEARCH_UNIVERSE_LIMIT")
    if settings.ai_provider not in {"openai", "ollama"}:
        raise ConfigError("AI_PROVIDER must be 'openai' or 'ollama'")
    if settings.ai_research_enabled and settings.ai_provider == "openai" and not settings.openai_api_key:
        raise ConfigError("OPENAI_API_KEY is required when AI_PROVIDER=openai and AI_RESEARCH_ENABLED=true")
    if settings.ai_research_enabled and settings.ai_provider == "ollama" and not settings.ollama_base_url:
        raise ConfigError("OLLAMA_BASE_URL is required when AI_PROVIDER=ollama and AI_RESEARCH_ENABLED=true")

    return settings
