"""Ligação com a Alpaca. Por padrão só fala com a conta paper (simulada)."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from ..models import Side, AssetClass, Bar, TradePlan
from .base import Broker, Fill, Position

LIVE_CONFIRMATION = "EU_ACEITO_O_RISCO"


class LiveTradingBlocked(RuntimeError):
    pass


def _timeframe(tf: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    table = {
        "1min": TimeFrame(1, TimeFrameUnit.Minute),
        "5min": TimeFrame(5, TimeFrameUnit.Minute),
        "15min": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "4h": TimeFrame(4, TimeFrameUnit.Hour),
        "1d": TimeFrame(1, TimeFrameUnit.Day),
    }
    if tf not in table:
        raise ValueError(f"timeframe não suportado: {tf}")
    return table[tf]


def _position_symbol(symbol: str) -> str:
    return symbol.replace("/", "")  # a API de posições usa BTCUSD


class AlpacaBroker(Broker):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        if not paper and os.environ.get("TRADE_CITY_LIVE") != LIVE_CONFIRMATION:
            raise LiveTradingBlocked(
                "Conta real bloqueada. Para liberar, defina TRADE_CITY_LIVE="
                f"{LIVE_CONFIRMATION} e TRADE_CITY_MODE=live, só depois da validação."
            )
        from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        self.paper = paper
        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.crypto_data = CryptoHistoricalDataClient(api_key, secret_key)
        self.stock_data = StockHistoricalDataClient(api_key, secret_key)

    @classmethod
    def from_env(cls) -> "AlpacaBroker":
        key, secret = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Defina ALPACA_API_KEY e ALPACA_SECRET_KEY (veja .env.example).")
        mode = os.environ.get("TRADE_CITY_MODE", "paper").lower()
        return cls(key, secret, paper=(mode != "live"))

    # dados ----------------------------------------------------------------
    def get_bars(self, symbol, asset_class, timeframe, lookback_days, end: datetime | None = None):
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest

        end = end or datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        if asset_class is AssetClass.CRYPTO:
            req = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=_timeframe(timeframe), start=start, end=end)
            data = self.crypto_data.get_crypto_bars(req)
        else:
            req = StockBarsRequest(
                symbol_or_symbols=symbol, timeframe=_timeframe(timeframe), start=start, end=end, feed=DataFeed.IEX
            )
            data = self.stock_data.get_stock_bars(req)
        raw = data.data.get(symbol, [])
        bars = [Bar(b.timestamp, b.open, b.high, b.low, b.close, b.volume) for b in raw]
        return _drop_unclosed(bars, timeframe, datetime.now(timezone.utc))

    def latest_price(self, symbol, asset_class):
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import CryptoLatestTradeRequest, StockLatestTradeRequest

        if asset_class is AssetClass.CRYPTO:
            trade = self.crypto_data.get_crypto_latest_trade(CryptoLatestTradeRequest(symbol_or_symbols=symbol))
        else:
            trade = self.stock_data.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
            )
        return float(trade[symbol].price)

    # conta ----------------------------------------------------------------
    def buying_power(self):
        account = self.trading.get_account()
        return float(account.non_marginable_buying_power or account.cash)

    def is_market_open(self, asset_class):
        if asset_class is AssetClass.CRYPTO:
            return True
        return bool(self.trading.get_clock().is_open)

    def get_position(self, symbol):
        from alpaca.common.exceptions import APIError

        try:
            pos = self.trading.get_open_position(_position_symbol(symbol))
        except APIError as exc:
            if getattr(exc, "status_code", None) == 404 or "position does not exist" in str(exc).lower():
                return None
            raise
        return Position(symbol, float(pos.qty), float(pos.avg_entry_price))

    # ordens ---------------------------------------------------------------
    def submit_entry(self, plan: TradePlan, asset_class):
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

        symbol = plan.signal.symbol
        if asset_class is AssetClass.EQUITY:
            req = MarketOrderRequest(
                symbol=symbol,
                qty=int(plan.qty),
                side=OrderSide.BUY if plan.side is Side.LONG else OrderSide.SELL,
                time_in_force=TimeInForce.DAY if plan.side is Side.SHORT else TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(plan.take_profit, 2)),
                stop_loss=StopLossRequest(stop_price=round(plan.stop_loss, 2)),
            )
        else:
            # cripto na Alpaca não aceita ordem com stops anexados: a mesa vigia os stops
            req = MarketOrderRequest(symbol=symbol, qty=plan.qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        order = self.trading.submit_order(req)
        return self._wait_fill(str(order.id), fallback_price=plan.entry, fallback_qty=plan.qty)

    def close_position(self, symbol):
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        open_orders = self.trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
        for order in open_orders:
            self.trading.cancel_order_by_id(order.id)
        order = self.trading.close_position(_position_symbol(symbol))
        return self._wait_fill(str(order.id), fallback_price=self.latest_price_any(symbol), fallback_qty=0.0)

    def last_exit_price(self, symbol):
        from alpaca.trading.enums import OrderSide, QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        orders = self.trading.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.CLOSED, symbols=[symbol], side=OrderSide.SELL, limit=20, nested=False)
        )
        filled = [o for o in orders if o.filled_at is not None and o.filled_avg_price is not None]
        if not filled:
            return None
        latest = max(filled, key=lambda o: o.filled_at)
        return float(latest.filled_avg_price)

    # apoio ----------------------------------------------------------------
    def latest_price_any(self, symbol: str) -> float:
        asset_class = AssetClass.CRYPTO if "/" in symbol else AssetClass.EQUITY
        return self.latest_price(symbol, asset_class)

    def _wait_fill(self, order_id: str, fallback_price: float, fallback_qty: float, timeout: float = 15.0) -> Fill:
        from alpaca.trading.enums import OrderStatus

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            order = self.trading.get_order_by_id(order_id)
            if order.status == OrderStatus.FILLED and order.filled_avg_price is not None:
                return Fill(order_id, float(order.filled_avg_price), float(order.filled_qty))
            time.sleep(1.0)
        return Fill(order_id, fallback_price, fallback_qty)


_TF_SECONDS = {"1min": 60, "5min": 300, "15min": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def _drop_unclosed(bars: list[Bar], timeframe: str, now: datetime) -> list[Bar]:
    """Remove o candle que ainda está em formação."""
    span = timedelta(seconds=_TF_SECONDS[timeframe])
    if timeframe == "1d":
        return [b for b in bars if b.ts.date() < now.date()] if bars else bars
    return [b for b in bars if b.ts + span <= now]
