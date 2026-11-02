"""Pure allocation math shared by the category split and the matching engine. No database, no I/O.

Same inputs always give the same output: ties break by id, and rounding uses largest remainder
so the cents always add up to exactly the amount being shared.
"""

import math
from collections.abc import Iterable, Mapping


def quadratic_score(contributions: Iterable[tuple[int, float]]) -> float:
    """P = (sum of w*sqrt(d))^2 - sum of (w*sqrt(d))^2 over people, d in cents and w their weight.

    With every weight 1 this is the design's (sum sqrt d)^2 - sum d: many small backers score
    higher than one large one. A guest card donor has w = 0.5.
    """
    roots = [w * math.sqrt(d) for d, w in contributions if d > 0]
    return sum(roots) ** 2 - sum(r * r for r in roots)


def split(amount: int, weights: Mapping[int, float]) -> dict[int, int]:
    """Share `amount` cents in proportion to weights. All-zero weights share equally."""
    if not weights:
        return {}
    ids = sorted(weights)
    total = sum(weights[i] for i in ids)
    if total <= 0:
        return split(amount, {i: 1 for i in ids})
    exact = {i: amount * weights[i] / total for i in ids}
    out = {i: math.floor(exact[i]) for i in ids}
    # Hand out the leftover cents to the largest remainders, lowest id first on ties.
    for i in sorted(ids, key=lambda i: (-(exact[i] - out[i]), i))[: amount - sum(out.values())]:
        out[i] += 1
    return out


def crowd_split(amount: int, scores: Mapping[int, float], floor_pct: float = 20.0) -> dict[int, int]:
    """Design Step 3: floor_pct shared equally, the rest by score. No scores yet: all equally."""
    if not scores:
        return {}
    if sum(scores.values()) <= 0:
        return split(amount, {i: 1 for i in scores})
    floor = round(amount * floor_pct / 100)
    equal = split(floor, {i: 1 for i in scores})
    crowd = split(amount - floor, scores)
    return {i: equal[i] + crowd[i] for i in scores}


def closest_to_goal_split(amount: int, remaining: Mapping[int, int]) -> dict[int, int]:
    """Fill the project nearest its goal first, then the next. Money left once all are full is shared equally."""
    out = {i: 0 for i in remaining}
    left = amount
    for i in sorted((i for i in remaining if remaining[i] > 0), key=lambda i: (remaining[i], i)):
        give = min(left, remaining[i])
        out[i] += give
        left -= give
        if left == 0:
            return out
    for i, extra in split(left, {i: 1 for i in remaining}).items():
        out[i] += extra
    return out
