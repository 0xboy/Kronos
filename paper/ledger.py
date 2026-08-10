"""Persistent sleeve ledger: only positions this strategy bought.

File: paper_results/sleeve_ledger.json
Tracks open holdings + full trade history so the runner never touches
manual / foreign Alpaca positions outside the sleeve.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "paper_results" / "sleeve_ledger.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_ledger(budget: float = 0.0) -> dict[str, Any]:
    return {
        "budget": float(budget),  # 0 = full-cash mode; runner may overwrite with equity
        "updated_at": _now(),
        "holdings": {},  # symbol -> {qty, avg_cost, cost_basis, opened_at}
        "trades": [],
    }


def load_ledger(path: Path | None = None) -> dict[str, Any]:
    path = path or DEFAULT_PATH
    if not path.exists():
        return empty_ledger()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("budget", 0.0)
    data.setdefault("holdings", {})
    data.setdefault("trades", [])
    data.setdefault("updated_at", _now())
    return data


def save_ledger(ledger: dict[str, Any], path: Path | None = None) -> Path:
    path = path or DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger["updated_at"] = _now()
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return path


def holding_symbols(ledger: dict[str, Any]) -> set[str]:
    return {sym for sym, h in ledger.get("holdings", {}).items() if float(h.get("qty", 0)) > 0}


def holding_qty(ledger: dict[str, Any], symbol: str) -> float:
    h = ledger.get("holdings", {}).get(symbol)
    if not h:
        return 0.0
    return float(h.get("qty", 0))


def record_buy(
    ledger: dict[str, Any],
    *,
    symbol: str,
    qty: float,
    price: float,
    order_id: str | None = None,
    expected_return: float | None = None,
    run_id: str | None = None,
) -> None:
    qty = float(qty)
    price = float(price)
    if qty <= 0:
        return
    notional = qty * price
    holdings = ledger.setdefault("holdings", {})
    cur = holdings.get(symbol)
    if cur and float(cur.get("qty", 0)) > 0:
        old_qty = float(cur["qty"])
        old_basis = float(cur.get("cost_basis", old_qty * float(cur.get("avg_cost", price))))
        new_qty = old_qty + qty
        new_basis = old_basis + notional
        holdings[symbol] = {
            "qty": new_qty,
            "avg_cost": new_basis / new_qty if new_qty else price,
            "cost_basis": new_basis,
            "opened_at": cur.get("opened_at", _now()),
        }
    else:
        holdings[symbol] = {
            "qty": qty,
            "avg_cost": price,
            "cost_basis": notional,
            "opened_at": _now(),
        }
    ledger.setdefault("trades", []).append(
        {
            "ts": _now(),
            "side": "buy",
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "notional": round(notional, 2),
            "order_id": order_id,
            "expected_return": expected_return,
            "run_id": run_id,
        }
    )


def record_sell(
    ledger: dict[str, Any],
    *,
    symbol: str,
    qty: float,
    price: float,
    order_id: str | None = None,
    expected_return: float | None = None,
    run_id: str | None = None,
) -> None:
    qty = float(qty)
    price = float(price)
    if qty <= 0:
        return
    holdings = ledger.setdefault("holdings", {})
    cur = holdings.get(symbol)
    if cur:
        left = float(cur.get("qty", 0)) - qty
        if left <= 1e-9:
            holdings.pop(symbol, None)
        else:
            avg = float(cur.get("avg_cost", price))
            holdings[symbol] = {
                "qty": left,
                "avg_cost": avg,
                "cost_basis": left * avg,
                "opened_at": cur.get("opened_at", _now()),
            }
    ledger.setdefault("trades", []).append(
        {
            "ts": _now(),
            "side": "sell",
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "notional": round(qty * price, 2),
            "order_id": order_id,
            "expected_return": expected_return,
            "run_id": run_id,
        }
    )


def drop_holding(ledger: dict[str, Any], symbol: str, *, reason: str, run_id: str | None = None) -> None:
    """Remove a ledger name that no longer exists at the broker."""
    holdings = ledger.setdefault("holdings", {})
    cur = holdings.pop(symbol, None)
    if not cur:
        return
    ledger.setdefault("trades", []).append(
        {
            "ts": _now(),
            "side": "sync_drop",
            "symbol": symbol,
            "qty": float(cur.get("qty", 0)),
            "price": float(cur.get("avg_cost", 0)),
            "notional": round(float(cur.get("cost_basis", 0)), 2),
            "order_id": None,
            "expected_return": None,
            "run_id": run_id,
            "note": reason,
        }
    )
