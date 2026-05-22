from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from .config import Settings

LOGGER = logging.getLogger(__name__)


class MarketDataService:
    def __init__(self, settings: Settings) -> None:
        self.client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )

    def get_recent_bars(self, symbols: list[str], lookback_days: int = 40) -> dict[str, pd.DataFrame]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days * 2)
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment="raw",
            feed="iex",
        )
        bars = self.client.get_stock_bars(request)
        frames: dict[str, pd.DataFrame] = {}

        for symbol in symbols:
            raw = bars.df.loc[symbol] if not bars.df.empty and symbol in bars.df.index.get_level_values(0) else pd.DataFrame()
            if raw.empty:
                LOGGER.warning("No market data returned for %s", symbol)
                frames[symbol] = pd.DataFrame(columns=["close", "volume"])
                continue

            frame = raw.reset_index().sort_values("timestamp").tail(lookback_days).copy()
            frame = frame[["timestamp", "close", "volume"]]
            frame["close"] = frame["close"].astype(float)
            frame["volume"] = frame["volume"].astype(float)
            frames[symbol] = frame.reset_index(drop=True)

        return frames
