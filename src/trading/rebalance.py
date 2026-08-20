"""Sleeve rebalance planning (pure logic; broker I/O stays in CLIs)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from config.paths import PAPER_RESULTS
from inference.signals import Signal
from trading.ledger import holding_symbols, record_buy
from trading.sizing import conviction


@dataclass(frozen=True)
class SleeveBudget:
    sleeve_budget: float
    kept_value: float
    deployable: float
    label: str
    ledger_budget: float


def sleeve_kept_value(
    held: set[str],
    qty_by_sym: dict[str, float],
    alpaca_by_sym: dict[str, dict],
    signal_price: dict[str, float],
) -> float:
    """Mark-to-market value of sleeve names still held."""
    total = 0.0
    for sym in held:
        if sym in alpaca_by_sym:
            total += float(alpaca_by_sym[sym]["market_value"])
            continue
        px = signal_price.get(sym)
        qty = qty_by_sym.get(sym, 0.0)
        if px is not None and qty > 0:
            total += qty * px
    return total


def compute_deployable(cash: float, buying_power: float, *, haircut: float = 0.995) -> float:
    """Cash available to deploy after a small BP haircut."""
    return max(0.0, min(float(cash), float(buying_power)) * float(haircut))


def compute_sleeve_budget(
    kept_value: float,
    deployable: float,
    *,
    notional_cap: float,
    equity: float | None = None,
) -> SleeveBudget:
    """Resolve sleeve NAV / cap used for sizing."""
    kept = float(kept_value)
    dep = float(deployable)
    cap = float(notional_cap)
    if cap > 0:
        return SleeveBudget(
            sleeve_budget=cap,
            kept_value=kept,
            deployable=dep,
            label=f"sleeve_cap=${cap:.0f} kept=${kept:.0f} cash=${dep:.0f}",
            ledger_budget=cap,
        )
    nav = kept + dep
    eq = float(equity) if equity is not None else nav
    return SleeveBudget(
        sleeve_budget=nav,
        kept_value=kept,
        deployable=dep,
        label=(
            f"full-rebalance nav=${nav:.0f} "
            f"kept=${kept:.0f} cash=${dep:.0f}"
        ),
        ledger_budget=eq,
    )


def signals_flagged_to_sell(
    signals: Sequence[Signal],
    held: set[str],
    sell_below: float,
) -> list[Signal]:
    """Sleeve holds whose predicted return fell below the sell threshold."""
    return [s for s in signals if s.symbol in held and s.expected_return < sell_below]


def select_rebalance_target(
    signals: Sequence[Signal],
    *,
    held: set[str],
    min_return: float,
    top_k: int,
) -> tuple[list[Signal], list[Signal]]:
    """Pick conviction top-K target sleeve and holds to rotate out."""
    ranked = sorted(
        [s for s in signals if s.expected_return >= min_return],
        key=lambda s: conviction(s.score, s.expected_return),
        reverse=True,
    )
    target = ranked[: max(0, int(top_k))]
    target_syms = {s.symbol for s in target}
    by_sym = {s.symbol: s for s in signals}
    exits = [
        by_sym[sym]
        for sym in sorted(held)
        if sym not in target_syms and sym in by_sym
    ]
    return target, exits


def select_cash_add_candidates(
    signals: Sequence[Signal],
    *,
    held: set[str],
    min_return: float,
    top_k: int,
) -> list[Signal]:
    """Legacy no-rebalance path: fill remaining top-K slots with new names only."""
    buy_slots = max(0, int(top_k) - len(held))
    return [
        s
        for s in signals
        if s.expected_return >= min_return and s.symbol not in held
    ][:buy_slots]


def seed_ledger_from_latest_run(
    ledger: dict[str, Any],
    broker_syms: set[str],
    *,
    runs_dir: Path | None = None,
) -> list[str]:
    """If sleeve is empty, adopt historical submit buys still held at the broker."""
    if holding_symbols(ledger):
        return []
    root = runs_dir if runs_dir is not None else (PAPER_RESULTS / "runs")
    runs = sorted(root.glob("run_*.json"), reverse=True)
    claimed: set[str] = set()
    seeded: list[str] = []
    for path in runs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if data.get("dry_run", True):
            continue
        for o in data.get("orders", []):
            if o.get("side") != "buy" or not o.get("submitted"):
                continue
            sym = o["symbol"]
            if sym not in broker_syms or sym in claimed:
                continue
            qty = float(o.get("qty") or 0)
            px = float(o.get("last_close") or 0)
            if qty <= 0 or px <= 0:
                continue
            record_buy(
                ledger,
                symbol=sym,
                qty=qty,
                price=px,
                order_id=o.get("order_id"),
                expected_return=o.get("expected_return"),
                run_id=f"seed:{path.name}",
            )
            claimed.add(sym)
            seeded.append(sym)
    return seeded
