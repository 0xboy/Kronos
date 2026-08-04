from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


@dataclass
class OrderResult:
    symbol: str
    qty: float
    side: str
    submitted: bool
    order_id: str | None
    message: str


def make_trading_client(api_key: str, secret_key: str, paper: bool = True) -> TradingClient:
    return TradingClient(api_key, secret_key, paper=paper)


def market_is_open(client: TradingClient) -> bool:
    """True only during regular US equity session (not overnight / weekend)."""
    clock = client.get_clock()
    return bool(clock.is_open)


def account_snapshot(client: TradingClient) -> dict:
    acct = client.get_account()
    return {
        "status": str(acct.status),
        "equity": float(acct.equity),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "paper": True,
    }


def held_symbols(client: TradingClient) -> set[str]:
    return {str(p.symbol) for p in client.get_all_positions()}


def list_positions(client: TradingClient) -> list[dict]:
    """Open positions with qty / price / market value."""
    out: list[dict] = []
    for p in client.get_all_positions():
        out.append(
            {
                "symbol": str(p.symbol),
                "qty": float(p.qty),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
            }
        )
    return out


def submit_market_sell(
    client: TradingClient,
    symbol: str,
    qty: float,
    dry_run: bool = True,
) -> OrderResult:
    if qty <= 0:
        return OrderResult(symbol, qty, "sell", False, None, "qty <= 0")

    if dry_run:
        return OrderResult(symbol, qty, "sell", False, None, "dry_run (no order sent)")

    order = client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
    )
    return OrderResult(
        symbol=symbol,
        qty=qty,
        side="sell",
        submitted=True,
        order_id=str(order.id),
        message="submitted",
    )


def position_qty(client: TradingClient, symbol: str) -> float:
    for p in client.get_all_positions():
        if str(p.symbol) == symbol:
            return float(p.qty)
    return 0.0


def submit_market_buy(
    client: TradingClient,
    symbol: str,
    qty: float,
    dry_run: bool = True,
) -> OrderResult:
    if qty <= 0:
        return OrderResult(symbol, qty, "buy", False, None, "qty <= 0")

    if dry_run:
        return OrderResult(symbol, qty, "buy", False, None, "dry_run (no order sent)")

    order = client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
    )
    return OrderResult(
        symbol=symbol,
        qty=qty,
        side="buy",
        submitted=True,
        order_id=str(order.id),
        message="submitted",
    )
