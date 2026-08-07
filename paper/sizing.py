"""Portfolio position sizing: equal vs score-weighted sleeves."""
from __future__ import annotations

import math
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


def conviction(score: float, expected_return: float) -> float:
    """Positive weight mass for sizing. Prefer score when set; else expected return."""
    if score and score > 0:
        return float(score)
    return max(0.0, float(expected_return))


def normalize_weights(
    raw: Sequence[float],
    *,
    max_weight: float = 0.30,
) -> list[float]:
    """Turn non-negative raw scores into weights that sum to 1 (or 0 if all zero).

    Caps each name at ``max_weight`` then renormalizes (iterative).
    ``max_weight <= 0`` or ``>= 1`` disables the cap.
    """
    vals = [max(0.0, float(x)) for x in raw]
    total = sum(vals)
    if total <= 0:
        return [0.0] * len(vals)

    w = [v / total for v in vals]
    cap = float(max_weight)
    if not (0.0 < cap < 1.0):
        return w

    # Iteratively clip and redistribute residual among uncapped names.
    for _ in range(len(w) + 2):
        over = [i for i, wi in enumerate(w) if wi > cap + 1e-12]
        if not over:
            break
        for i in over:
            w[i] = cap
        free = 1.0 - sum(w)
        if free <= 1e-12:
            break
        pool = [i for i, wi in enumerate(w) if wi < cap - 1e-12]
        if not pool:
            break
        pool_mass = sum(w[i] for i in pool)
        if pool_mass <= 1e-12:
            share = free / len(pool)
            for i in pool:
                w[i] = min(cap, w[i] + share)
        else:
            for i in pool:
                w[i] = min(cap, w[i] + free * (w[i] / pool_mass))
    s = sum(w)
    if s > 0:
        w = [wi / s for wi in w]
    return w


def allocate_budget(
    items: Sequence[T],
    budget: float,
    *,
    price_fn: Callable[[T], float],
    score_fn: Callable[[T], float],
    mode: str = "score",
    max_weight: float = 0.30,
) -> tuple[list[tuple[T, int, float]], float]:
    """Allocate ``budget`` across ``items``.

    Returns ``([(item, qty, cost), ...], leftover)``.
    Names that cannot buy at least 1 share are dropped and mass redistributed.
    """
    if budget <= 0 or not items:
        return [], float(budget)

    mode = (mode or "score").lower().strip()
    active = list(items)

    while active:
        if mode == "equal":
            raw = [1.0] * len(active)
        else:
            raw = [max(0.0, float(score_fn(x))) for x in active]
            if sum(raw) <= 0:
                # No positive conviction — fall back to equal among survivors.
                raw = [1.0] * len(active)

        weights = normalize_weights(raw, max_weight=max_weight)
        trial: list[tuple[T, int, float]] = []
        dropped = False
        spent = 0.0
        for x, w in zip(active, weights):
            px = float(price_fn(x))
            if px <= 0 or w <= 0:
                dropped = True
                continue
            slice_budget = budget * w
            qty = math.floor(slice_budget / px)
            if qty < 1:
                dropped = True
                continue
            cost = qty * px
            if spent + cost > budget + 1e-6:
                # Trim one share if float edge; else skip name.
                qty = math.floor((budget - spent) / px)
                if qty < 1:
                    dropped = True
                    continue
                cost = qty * px
            trial.append((x, qty, cost))
            spent += cost

        if not trial:
            return [], float(budget)

        if dropped and len(trial) < len(active):
            # Retry with only names that cleared the 1-share floor.
            active = [t[0] for t in trial]
            continue

        return trial, float(budget - spent)

    return [], float(budget)
