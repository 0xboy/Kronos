"""
Kronos + Alpaca paper smoke / 50-stock signal test.

Usage:
  1) Put keys in .env (ALPACA_API_KEY, ALPACA_SECRET_KEY)
  2) Dry-run (default):   .venv/Scripts/python.exe scripts/run_alpaca_paper.py
  3) Submit paper buys:   .venv/Scripts/python.exe scripts/run_alpaca_paper.py --submit
  4) Quick 5-symbol test: .venv/Scripts/python.exe scripts/run_alpaca_paper.py --limit 5

Portfolio sleeve:
  --notional 0      → deploy all account cash/equity into score-weighted rebalance (default)
  --notional N      → cap sleeve at $N; rebalance within that book
  --no-rebalance    → old behavior: only sell negatives + buy new names with leftover cash
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
from paper.data import (
    drop_split_discontinuities,
    fetch_daily_bars,
    make_data_client,
)
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
from paper.models import DEFAULT_PAPER_MODEL, model_label, resolve_model_id
from paper.signals import device_summary, load_predictor, score_symbol
from paper.sizing import allocate_budget, conviction, plan_rebalance
from paper.universe import UNIVERSE_100


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
    p.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Max sleeve names total (holds + new buys); buys fill remaining slots only",
    )
    p.add_argument(
        "--weight-mode",
        choices=("score", "equal"),
        default="score",
        help="Buy sizing: score = conviction-weighted (default), equal = 1/n",
    )
    p.add_argument(
        "--max-weight",
        type=float,
        default=0.30,
        help="Cap per-name weight when --weight-mode=score (0 disables)",
    )
    p.add_argument(
        "--notional",
        type=float,
        default=0.0,
        help="Sleeve $ budget (0 = full account; >0 = cap after kept holds)",
    )
    p.add_argument(
        "--rebalance",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Score-weight full sleeve (trim/add holds). --no-rebalance = cash-only adds",
    )
    p.add_argument(
        "--min-trade",
        type=float,
        default=25.0,
        help="Skip rebalance legs smaller than this $ notional",
    )
    p.add_argument("--submit", action="store_true", help="Actually submit paper market orders")
    p.add_argument(
        "--device",
        default="auto",
        help="Inference device: auto (CUDA if available), cuda, cuda:0, cpu",
    )
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
    p.add_argument(
        "--model",
        default=DEFAULT_PAPER_MODEL,
        help=(
            "Model alias or path. Aliases: spus-small-v1 (default FT), "
            "stock-small, stock-base, or any HF/local checkpoint path."
        ),
    )
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

    symbols = UNIVERSE_100[: args.limit] if args.limit and args.limit > 0 else list(UNIVERSE_100)
    dry_run = not args.submit
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    ledger = load_ledger(args.ledger)
    # budget field is bookkeeping only; buy sizing uses --notional / cash below

    print(f"Universe: {len(symbols)} symbols")
    print(f"Mode: {'DRY-RUN' if dry_run else 'SUBMIT PAPER ORDERS'}")
    print(
        f"Model: {model_label(args.model)} [{args.model}] -> {resolve_model_id(args.model)} "
        f"| lookback={args.lookback} pred_len={args.pred_len}"
    )
    print(f"Ledger: {args.ledger}")
    hw = device_summary(args.device)
    print(
        f"Compute: device={hw['device']}"
        + (f" gpu={hw['gpu']} vram={hw['vram_gb']}GB" if hw.get("gpu") else "")
        + f" torch={hw['torch']}"
    )

    trade = make_trading_client(settings.api_key, settings.secret_key, paper=True)
    data = make_data_client(settings.api_key, settings.secret_key)

    if args.submit and not args.allow_closed and not market_is_open(trade):
        print("US market is closed — skipping portfolio rebalance (use --allow-closed to override).")
        return 2

    snap = account_snapshot(trade)
    print(f"Account: equity=${snap['equity']:.2f} cash=${snap['cash']:.2f} bp=${snap['buying_power']:.2f}")

    print("Fetching daily bars from Alpaca (split+div adjusted)...")
    bars = fetch_daily_bars(data, symbols, lookback_trading_days=max(args.lookback + 50, 450))
    bars, split_drops = drop_split_discontinuities(bars, max_abs_ret=0.40)
    print(f"Got bars for {len(bars)}/{len(symbols)} symbols")
    skipped: list[tuple[str, str]] = []
    if split_drops:
        print(
            "Dropped split/jump artifacts: "
            + ", ".join(f"{s}(|r|={j:.0%})" for s, j in split_drops[:20])
            + ("..." if len(split_drops) > 20 else "")
        )
        for s, j in split_drops:
            skipped.append((s, f"price_discontinuity_|r|={j:.2%}"))

    print("Loading Kronos...")
    predictor = load_predictor(args.model, device=args.device)

    signals = []
    for i, symbol in enumerate(symbols, 1):
        df = bars.get(symbol)
        if df is None:
            if not any(sym == symbol for sym, _ in skipped):
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
    buying_power = float(snap.get("buying_power") or cash)
    if dry_run and sells:
        sold_notional = sum(float(o["notional_est"]) for o in orders if o["side"] == "sell")
        cash += sold_notional
        buying_power += sold_notional

    # Alpaca rejects if cost > buying_power; cash can look higher than BP briefly.
    deployable = min(cash, buying_power)
    deployable = max(0.0, deployable * 0.995)

    budget_cap = float(args.notional)
    if budget_cap > 0:
        sleeve_budget = budget_cap
        budget_label = f"sleeve_cap=${budget_cap:.0f} kept=${kept_value:.0f} cash=${cash:.0f}"
        ledger["budget"] = budget_cap
    else:
        sleeve_budget = kept_value + deployable
        budget_label = (
            f"full-rebalance nav=${sleeve_budget:.0f} "
            f"kept=${kept_value:.0f} cash=${cash:.0f} bp=${buying_power:.0f}"
        )
        ledger["budget"] = float(snap.get("equity") or sleeve_budget)

    print(f"\nSleeve budget: ${sleeve_budget:.2f} ({budget_label})")

    by_sym = {s.symbol: s for s in signals}

    def _submit_buy(s, qty: int, cost: float, *, tag: str = "buy") -> None:
        nonlocal already
        w_mass = conviction(s.score, s.expected_return)
        q = int(qty)
        c = float(cost)
        if not dry_run and s.last_close > 0:
            live = account_snapshot(trade)
            bp = max(0.0, float(live["buying_power"]) * 0.995)
            max_qty = math.floor(bp / float(s.last_close))
            if max_qty < q:
                print(f"  trim {s.symbol}: qty {q} -> {max_qty} (bp=${bp:.0f})")
                q = max_qty
                c = float(q) * float(s.last_close)
            if q < 1:
                orders.append(
                    {
                        "side": "buy",
                        "symbol": s.symbol,
                        "expected_return": s.expected_return,
                        "score": s.score,
                        "conviction": w_mass,
                        "last_close": s.last_close,
                        "pred_close": s.pred_close,
                        "qty": 0,
                        "notional_est": 0.0,
                        "weight_est": None,
                        "submitted": False,
                        "order_id": None,
                        "message": "skipped: insufficient buying power",
                        "tag": tag,
                    }
                )
                print(f"  BUY  {s.symbol}: skip (insufficient buying power)")
                return
        result = submit_market_buy(trade, s.symbol, float(q), dry_run=dry_run)
        orders.append(
            {
                "side": "buy",
                "symbol": s.symbol,
                "expected_return": s.expected_return,
                "score": s.score,
                "conviction": w_mass,
                "last_close": s.last_close,
                "pred_close": s.pred_close,
                "qty": q,
                "notional_est": round(c, 2),
                "weight_est": round(c / sleeve_budget, 4) if sleeve_budget > 0 else None,
                "submitted": result.submitted,
                "order_id": result.order_id,
                "message": result.message,
                "tag": tag,
            }
        )
        print(f"  BUY  {s.symbol}: qty={q} ~${c:.0f} (conv={w_mass:+.3f}) [{result.message}]")
        if result.submitted or (dry_run and q > 0):
            if result.submitted:
                record_buy(
                    ledger,
                    symbol=s.symbol,
                    qty=float(q),
                    price=float(s.last_close),
                    order_id=result.order_id,
                    expected_return=s.expected_return,
                    run_id=run_id,
                )
            already.add(s.symbol)
            if result.submitted and not dry_run:
                time.sleep(0.5)

    def _submit_sell(s, qty: float, *, tag: str = "sell") -> None:
        nonlocal already
        q = float(qty)
        if q <= 0:
            return
        result = submit_market_sell(trade, s.symbol, q, dry_run=dry_run)
        notional_est = round(q * s.last_close, 2)
        orders.append(
            {
                "side": "sell",
                "symbol": s.symbol,
                "expected_return": s.expected_return,
                "last_close": s.last_close,
                "pred_close": s.pred_close,
                "qty": q,
                "notional_est": notional_est,
                "submitted": result.submitted,
                "order_id": result.order_id,
                "message": result.message,
                "tag": tag,
            }
        )
        print(f"  SELL {s.symbol}: qty={q} ~${notional_est:.0f} [{result.message}]")
        if result.submitted:
            record_sell(
                ledger,
                symbol=s.symbol,
                qty=q,
                price=float(s.last_close),
                order_id=result.order_id,
                expected_return=s.expected_return,
                run_id=run_id,
            )
            already.discard(s.symbol)
            time.sleep(0.5)
        elif dry_run:
            already.discard(s.symbol)

    if args.rebalance:
        # Target = top_k by conviction among names still above min_return.
        ranked = sorted(
            [s for s in signals if s.expected_return >= args.min_return],
            key=lambda s: conviction(s.score, s.expected_return),
            reverse=True,
        )
        target = ranked[: args.top_k]
        target_syms = {s.symbol for s in target}

        # Rotate out holds that fell out of top_k (still non-negative but weaker).
        exits = [
            by_sym[sym]
            for sym in sorted(already)
            if sym not in target_syms and sym in by_sym
        ]
        print(
            f"\nRebalance target ({len(target)}): "
            + ", ".join(s.symbol for s in target)
        )
        print(f"Rotate exits: {len(exits)} {[s.symbol for s in exits]}")
        for s in exits:
            ledger_q = holding_qty(ledger, s.symbol)
            broker_q = position_qty(trade, s.symbol) if not dry_run else ledger_q
            qty = min(ledger_q, broker_q) if broker_q > 0 else ledger_q
            _submit_sell(s, qty, tag="rotate_out")

        if not dry_run and exits:
            time.sleep(1.5)
            snap = account_snapshot(trade)
            try:
                alpaca_positions = list_positions(trade)
                alpaca_by_sym = {p["symbol"]: p for p in alpaca_positions}
            except Exception:  # noqa: BLE001
                pass
            cash = float(snap["cash"])
            buying_power = float(snap.get("buying_power") or cash)
            deployable = max(0.0, min(cash, buying_power) * 0.995)
            qty_by_sym = {sym: holding_qty(ledger, sym) for sym in already}
            kept_value = sleeve_kept_value(already, qty_by_sym, alpaca_by_sym, signal_price)
            if budget_cap > 0:
                sleeve_budget = budget_cap
            else:
                sleeve_budget = kept_value + deployable
            print(f"Post-exit sleeve budget: ${sleeve_budget:.2f} (kept=${kept_value:.0f})")
        elif dry_run and exits:
            exit_val = sum(
                holding_qty(ledger, s.symbol) * s.last_close for s in exits
            )
            kept_value = max(0.0, kept_value - exit_val)
            deployable = deployable + exit_val
            if budget_cap > 0:
                sleeve_budget = budget_cap
            else:
                sleeve_budget = kept_value + deployable

        def _cur_qty(s) -> float:
            if dry_run:
                return float(holding_qty(ledger, s.symbol)) if s.symbol in already else 0.0
            return float(position_qty(trade, s.symbol))

        trades, leftover = plan_rebalance(
            target,
            sleeve_budget,
            price_fn=lambda s: s.last_close,
            score_fn=lambda s: conviction(s.score, s.expected_return),
            current_qty_fn=_cur_qty,
            mode=args.weight_mode,
            max_weight=args.max_weight,
            min_trade_value=args.min_trade,
        )
        print(
            f"Rebalance legs: {len(trades)} "
            f"(mode={args.weight_mode}, max_w={args.max_weight:.0%}, "
            f"min_trade=${args.min_trade:.0f}, leftover=${leftover:.2f})"
        )
        for s, side, qty, notional, tgt_v, cur_v in trades:
            print(
                f"  plan {side.upper():4} {s.symbol}: qty={qty} "
                f"~${notional:.0f}  cur=${cur_v:.0f} -> tgt=${tgt_v:.0f}"
            )
            if side == "sell":
                _submit_sell(s, float(qty), tag="rebalance_trim")
            else:
                _submit_buy(s, int(qty), float(notional), tag="rebalance_add")
    else:
        # Legacy: only deploy leftover cash into new names; holds untouched.
        buy_budget = deployable
        if budget_cap > 0:
            room = max(0.0, budget_cap - kept_value)
            buy_budget = min(deployable, room)
        print(f"Buy budget (no-rebalance): ${buy_budget:.2f}")
        buy_slots = max(0, int(args.top_k) - len(already))
        candidates = [
            s
            for s in signals
            if s.expected_return >= args.min_return and s.symbol not in already
        ][:buy_slots]
        buys, remaining = allocate_budget(
            candidates,
            buy_budget,
            price_fn=lambda s: s.last_close,
            score_fn=lambda s: conviction(s.score, s.expected_return),
            mode=args.weight_mode,
            max_weight=args.max_weight,
        )
        print(
            f"Selected buys: {len(buys)} "
            f"(held={len(already)}, buy_slots={buy_slots}, leftover=${remaining:.2f})"
        )
        for s, qty, cost in buys:
            _submit_buy(s, int(qty), float(cost), tag="cash_add")

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "run_id": run_id,
        "account": snap,
        "sleeve": {
            "budget": sleeve_budget,
            "kept_value": round(kept_value, 2),
            "deployable": round(deployable, 2),
            "holdings": sorted(holding_symbols(ledger)) if not dry_run else sorted(already),
            "ledger_path": str(args.ledger),
        },
        "params": {
            "lookback": args.lookback,
            "pred_len": args.pred_len,
            "min_return": args.min_return,
            "sell_below": args.sell_below,
            "top_k": args.top_k,
            "weight_mode": args.weight_mode,
            "max_weight": args.max_weight,
            "notional": args.notional,
            "rebalance": bool(args.rebalance),
            "min_trade": args.min_trade,
            "model": args.model,
            "model_label": model_label(args.model),
            "model_path": resolve_model_id(args.model),
            "device": hw,
            "symbols": symbols,
        },
        "signals": [
            {
                "symbol": s.symbol,
                "expected_return": s.expected_return,
                "score": s.score,
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
