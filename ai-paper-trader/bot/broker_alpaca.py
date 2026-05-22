from __future__ import annotations

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from .config import Settings


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

    def get_account(self):
        return self.client.get_account()

    def get_positions(self):
        return self.client.get_all_positions()

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
