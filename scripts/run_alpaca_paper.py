"""
Kronos + Alpaca paper smoke / 50-stock signal test.

Usage:
  1) Put keys in .env (ALPACA_API_KEY, ALPACA_SECRET_KEY)
  2) Dry-run (default):   .venv/Scripts/python.exe scripts/run_alpaca_paper.py
  3) Submit paper buys:   .venv/Scripts/python.exe scripts/run_alpaca_paper.py --submit
  4) Quick 5-symbol test: .venv/Scripts/python.exe scripts/run_alpaca_paper.py --limit 5

Portfolio sleeve:
  --notional 20000  → only trade within this $ budget; buys use leftover after kept holds
  --notional 0      → deploy all account cash
  Only positions recorded in paper_results/sleeve_ledger.json are managed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(ROOT))

from paper.broker import (
    account_snapshot,
    list_positions,
    make_trading_client,
    market_is_open,
    position_qty,
    submit_market_buy,
    submit_market_sell,
)
from paper.config import load_settings
from paper.data import fetch_daily_bars, make_data_client
from paper.ledger import (
    DEFAULT_PATH as LEDGER_DEFAULT,
    drop_holding,
    holding_qty,
    holding_symbols,
    load_ledger,
    record_buy,
    record_sell,
    save_ledger,
)
from paper.signals import load_predictor, score_symbol
from paper.universe import UNIVERSE_50


def seed_ledger_from_latest_run(ledger: dict, broker_syms: set[str]) -> list[str]:
    """If sleeve is empty, adopt historical submit buys still held at the broker."""
    if holding_symbols(ledger):
        return []
    runs = sorted((ROOT / "paper_results" / "runs").glob("run_*.json"), reverse=True)
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



def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kronos Alpaca paper test (50 stocks)")
    p.add_argument("--limit", type=int, default=0, help="Use first N symbols (0 = all 50)")
    p.add_argument("--lookback", type=int, default=400)
    p.add_argument("--pred-len", type=int, default=1, help="Forecast horizon in trading days")
    p.add_argument("--min-return", type=float, default=0.01, help="Min predicted return to buy")
    p.add_argument(
        "--sell-below",
        type=float,
        default=0.0,
        help="Sell sleeve name if predicted return is below this (default 0 = any negative)",
    )
    p.add_argument("--top-k", type=int, default=10, help="Max names to buy")
    p.add_argument(
        "--notional",
        type=float,
        default=20000.0,
        help="Sleeve $ budget: buys use remaining after kept holds. 0 = use all cash",
    )
    p.add_argument("--submit", action="store_true", help="Actually submit paper market orders")
    p.add_argument(
        "--allow-closed",
        action="store_true",
        help="Allow --submit even when the US market is closed (default: refuse)",
    )
    p.add_argument(
        "--ledger",
        type=Path,
        default=LEDGER_DEFAULT,
        help="Sleeve ledger JSON (holdings + trades)",
    )
    p.add_argument("--model", default="NeoQuasar/Kronos-small")
    return p.parse_args()


def _mark_kept_value(
    ledger_syms: set[str],
    alpaca_by_sym: dict[str, dict],
    signal_price: dict[str, float],
) -> float:
    total = 0.0
    for sym in ledger_syms:
        if sym in alpaca_by_sym:
            total += float(alpaca_by_sym[sym]["market_value"])
        elif sym in signal_price:
            total += holding_qty  # placeholder — fixed below
    # recompute properly
    total = 0.0
    for sym in ledger_syms:
        qty = None
        px = None
        if sym in alpaca_by_sym:
            total += float(alpaca_by_sym[sym]["market_value"])
            continue
        # fallback: ledger qty * last signal/close
        from paper.ledger import load_ledger as _  # noqa: F401 — avoid circular; use caller qty map

        px = signal_price.get(sym)
        if px is None:
            continue
    return total


def sleeve_kept_value(
    held: set[str],
    qty_by_sym: dict[str, float],
    alpaca_by_sym: dict[str, dict],
    signal_price: dict[str, float],
) -> float:
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


def main() -> int:
    args = parse_args()
    settings = load_settings()

    if not settings.configured:
        print("Missing Alpaca keys.")
        print(f"Edit: {ROOT / '.env'}")
        print("Need: ALPACA_API_KEY and ALPACA_SECRET_KEY (Paper Trading)")
        return 1

    if not settings.paper:
        print("Refusing to run: ALPACA_PAPER is not true. Set ALPACA_PAPER=true.")
        return 1

    symbols = UNIVERSE_50[: args.limit] if args.limit and args.limit > 0 else list(UNIVERSE_50)
    dry_run = not args.submit
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    ledger = load_ledger(args.ledger)
    if args.notional > 0:
        ledger["budget"] = float(args.notional)

    print(f"Universe: {len(symbols)} symbols")
    print(f"Mode: {'DRY-RUN' if dry_run else 'SUBMIT PAPER ORDERS'}")
    print(f"Model: {args.model} | lookback={args.lookback} pred_len={args.pred_len}")
    print(f"Ledger: {args.ledger}")

    trade = make_trading_client(settings.api_key, settings.secret_key, paper=True)
    data = make_data_client(settings.api_key, settings.secret_key)

    if args.submit and not args.allow_closed and not market_is_open(trade):
        print("US market is closed — skipping portfolio rebalance (use --allow-closed to override).")
        return 2

    snap = account_snapshot(trade)
    print(f"Account: equity=${snap['equity']:.2f} cash=${snap['cash']:.2f} bp=${snap['buying_power']:.2f}")

    print("Fetching daily bars from Alpaca...")
    bars = fetch_daily_bars(data, symbols, lookback_trading_days=max(args.lookback + 50, 450))
    print(f"Got bars for {len(bars)}/{len(symbols)} symbols")

    print("Loading Kronos...")
    predictor = load_predictor(args.model)

    signals = []
    skipped = []
    for i, symbol in enumerate(symbols, 1):
        df = bars.get(symbol)
        if df is None:
            skipped.append((symbol, "no bars"))
            continue
        print(f"[{i}/{len(symbols)}] scoring {symbol} ({len(df)} bars)...")
        try:
            sig = score_symbol(
                predictor,
                symbol,
                df,
                lookback=args.lookback,
                pred_len=args.pred_len,
            )
        except Exception as exc:  # noqa: BLE001 — keep batch running
            skipped.append((symbol, str(exc)))
            continue
        if sig is None:
            skipped.append((symbol, f"need>={args.lookback} bars, have {len(df)}"))
            continue
        signals.append(sig)
        print(f"  -> ret={sig.expected_return:+.2%} last={sig.last_close:.2f} pred={sig.pred_close:.2f}")

    signals.sort(key=lambda s: s.expected_return, reverse=True)
    signal_price = {s.symbol: float(s.last_close) for s in signals}

    # Sleeve universe = only what THIS strategy recorded as bought.
    already = holding_symbols(ledger)
    try:
        alpaca_positions = list_positions(trade)
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: could not fetch positions ({exc})")
        alpaca_positions = []
    alpaca_by_sym = {p["symbol"]: p for p in alpaca_positions}
    alpaca_all = set(alpaca_by_sym)

    # Drop ledger names the user closed manually outside this runner.
    stale = sorted(already - alpaca_all)
    for sym in stale:
        print(f"Sync: {sym} in ledger but not at broker — dropping from sleeve")
        if not dry_run:
            drop_holding(ledger, sym, reason="missing_at_broker", run_id=run_id)
        already.discard(sym)

    foreign = sorted(alpaca_all - already)
    if foreign:
        print(f"Ignoring non-sleeve Alpaca positions: {foreign}")

    if already:
        print(f"Sleeve held: {sorted(already)}")
    else:
        print("Sleeve held: (empty)")

    print("\n=== Ranked signals ===")
    for s in signals:
        if s.symbol in already and s.expected_return < args.sell_below:
            flag = "SELL"
        elif s.expected_return >= args.min_return and s.symbol not in already:
            flag = "BUY"
        elif s.symbol in already:
            flag = "HOLD"
        else:
            flag = "skip"
        print(f"{s.symbol:6} {s.expected_return:+7.2%}  {flag}")

    # 1) Sell only sleeve holdings that flipped below threshold
    sells = [
        s
        for s in signals
        if s.symbol in already and s.expected_return < args.sell_below
    ]
    # Also sell sleeve holds we couldn't score (optional: keep them). Keep unscored.
    orders: list[dict] = []
    print(f"\nSelected sells: {len(sells)} (sell_below={args.sell_below:.2%})")
    for s in sells:
        ledger_q = holding_qty(ledger, s.symbol)
        broker_q = position_qty(trade, s.symbol)
        qty = min(ledger_q, broker_q) if broker_q > 0 else ledger_q
        if qty <= 0:
            print(f"  SELL {s.symbol}: skip (qty=0)")
            continue
        result = submit_market_sell(trade, s.symbol, qty, dry_run=dry_run)
        notional_est = round(qty * s.last_close, 2)
        orders.append(
            {
                "side": "sell",
                "symbol": s.symbol,
                "expected_return": s.expected_return,
                "last_close": s.last_close,
                "pred_close": s.pred_close,
                "qty": qty,
                "notional_est": notional_est,
                "submitted": result.submitted,
                "order_id": result.order_id,
                "message": result.message,
            }
        )
        print(f"  SELL {s.symbol}: qty={qty} ~${notional_est:.0f} [{result.message}]")
        if result.submitted or dry_run:
            # dry_run: still preview budget as if sold; only persist on submit
            if result.submitted:
                record_sell(
                    ledger,
                    symbol=s.symbol,
                    qty=qty,
                    price=float(s.last_close),
                    order_id=result.order_id,
                    expected_return=s.expected_return,
                    run_id=run_id,
                )
            already.discard(s.symbol)

    if not dry_run and any(o.get("submitted") for o in orders if o["side"] == "sell"):
        time.sleep(2)
        snap = account_snapshot(trade)
        try:
            alpaca_positions = list_positions(trade)
            alpaca_by_sym = {p["symbol"]: p for p in alpaca_positions}
        except Exception:  # noqa: BLE001
            pass

    qty_by_sym = {sym: holding_qty(ledger, sym) for sym in already}
    # For dry-run budget, pretend sells already left the sleeve.
    if dry_run:
        sell_set = {s.symbol for s in sells}
        preview_held = already - sell_set
        qty_by_sym = {sym: holding_qty(ledger, sym) for sym in preview_held}
        kept_value = sleeve_kept_value(preview_held, qty_by_sym, alpaca_by_sym, signal_price)
        # remove sold notionals from alpaca marks for sold names
        for s in sells:
            if s.symbol in alpaca_by_sym:
                # already excluded via preview_held
                pass
    else:
        kept_value = sleeve_kept_value(already, qty_by_sym, alpaca_by_sym, signal_price)

    cash = float(snap["cash"])
    if dry_run and sells:
        cash += sum(float(o["notional_est"]) for o in orders if o["side"] == "sell")

    budget = float(args.notional)
    if budget > 0:
        room = max(0.0, budget - kept_value)
        buy_budget = min(cash, room)
        budget_label = f"sleeve=${budget:.0f} kept=${kept_value:.0f} room=${room:.0f}"
    else:
        buy_budget = max(0.0, cash)
        budget_label = f"full-cash=${cash:.0f}"

    print(f"\nBuy budget: ${buy_budget:.2f} ({budget_label}, cash=${cash:.2f})")

    # 2) Buy with remaining sleeve room only
    candidates = [
        s
        for s in signals
        if s.expected_return >= args.min_return and s.symbol not in already
    ][: args.top_k]

    buys: list[tuple] = []
    remaining = buy_budget
    if buy_budget > 0 and candidates:
        for n in range(len(candidates), 0, -1):
            slice_budget = buy_budget / n
            trial = []
            spent = 0.0
            for s in candidates[:n]:
                qty = math.floor(slice_budget / s.last_close)
                if qty < 1:
                    continue
                cost = qty * s.last_close
                if spent + cost > buy_budget + 1e-6:
                    continue
                trial.append((s, qty, cost))
                spent += cost
            if trial:
                buys = trial
                remaining = buy_budget - spent
                break

    print(
        f"Selected buys: {len(buys)} "
        f"(min_return={args.min_return:.2%}, top_k={args.top_k}, leftover=${remaining:.2f})"
    )

    for s, qty, cost in buys:
        result = submit_market_buy(trade, s.symbol, float(qty), dry_run=dry_run)
        orders.append(
            {
                "side": "buy",
                "symbol": s.symbol,
                "expected_return": s.expected_return,
                "last_close": s.last_close,
                "pred_close": s.pred_close,
                "qty": qty,
                "notional_est": round(cost, 2),
                "submitted": result.submitted,
                "order_id": result.order_id,
                "message": result.message,
            }
        )
        print(f"  BUY  {s.symbol}: qty={qty} ~${cost:.0f} [{result.message}]")
        if result.submitted:
            record_buy(
                ledger,
                symbol=s.symbol,
                qty=float(qty),
                price=float(s.last_close),
                order_id=result.order_id,
                expected_return=s.expected_return,
                run_id=run_id,
            )
            already.add(s.symbol)

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "run_id": run_id,
        "account": snap,
        "sleeve": {
            "budget": budget,
            "kept_value": round(kept_value, 2),
            "buy_budget": round(buy_budget, 2),
            "holdings": sorted(holding_symbols(ledger)) if not dry_run else sorted(already),
            "ledger_path": str(args.ledger),
        },
        "params": {
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "min_return": args.min_return,
            "sell_below": args.sell_below,
            "top_k": args.top_k,
            "notional": args.notional,
            "model": args.model,
            "symbols": symbols,
        },
        "signals": [
            {
                "symbol": s.symbol,
                "expected_return": s.expected_return,
                "last_close": s.last_close,
                "pred_close": s.pred_close,
                "bars": s.bars,
            }
            for s in signals
        ],
        "orders": orders,
        "skipped": [{"symbol": s, "reason": r} for s, r in skipped],
    }

    out_dir = ROOT / "paper_results" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"run_{run_id}.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved report -> {out_path}")

    if not dry_run:
        ledger_path = save_ledger(ledger, args.ledger)
        print(f"Saved sleeve ledger -> {ledger_path}")
        print(f"Sleeve holdings now: {sorted(holding_symbols(ledger))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
