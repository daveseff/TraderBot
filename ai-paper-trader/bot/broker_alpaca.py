from __future__ import annotations

import logging

from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.requests import MarketMoversRequest, MostActivesRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetExchange, AssetStatus
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.requests import MarketOrderRequest

from .config import Settings

LOGGER = logging.getLogger(__name__)


class AlpacaPaperBroker:
    def __init__(self, settings: Settings) -> None:
        if not settings.alpaca_paper:
            raise ValueError("Paper mode is required.")
        self.settings = settings
        self.client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=True,
        )
        self.screener_client = ScreenerClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )

    def get_account(self):
        return self.client.get_account()

    def get_positions(self):
        return self.client.get_all_positions()

    def get_clock(self):
        return self.client.get_clock()

    def list_tradable_symbols(self, limit: int) -> list[str]:
        request = GetAssetsRequest(
            status=AssetStatus.ACTIVE,
            asset_class=AssetClass.US_EQUITY,
        )
        assets = self.client.get_all_assets(filter=request)
        tradable_symbols = {
            asset.symbol
            if getattr(asset, "tradable", False)
            and getattr(asset, "fractionable", False)
            and getattr(asset, "exchange", None) not in {AssetExchange.OTC}
            else None
            for asset in assets
        }
        tradable_symbols.discard(None)

        most_active_top = min(max(limit, 10), 100)
        actives = self.screener_client.get_most_actives(MostActivesRequest(top=most_active_top, by="volume"))
        movers = self.screener_client.get_market_movers(MarketMoversRequest(top=min(max(limit // 2, 10), 50)))

        discovered: list[str] = []
        for row in actives.most_actives:
            symbol = row.symbol
            if symbol in tradable_symbols and symbol not in discovered:
                discovered.append(symbol)

        for row in movers.gainers:
            symbol = row.symbol
            if symbol in tradable_symbols and symbol not in discovered:
                discovered.append(symbol)

        LOGGER.info("Screener returned %d tradable research symbols.", len(discovered))
        return discovered[:limit]

    def submit_market_buy_notional(self, symbol: str, notional: float):
        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_data=order)

    def submit_market_sell_qty(self, symbol: str, qty: float):
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_data=order)

    def close_all_positions(self):
        return self.client.close_all_positions(cancel_orders=True)
