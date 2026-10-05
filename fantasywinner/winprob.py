"""Monte Carlo win probability for a head-to-head matchup."""
import numpy as np

from .models import Player


def simulate(lineup: list[Player], n: int, rng) -> np.ndarray:
    total = np.zeros(n)
    for p in lineup:
        # Gamma-ish skew is overkill here; a floored normal is good enough.
        total += np.maximum(0, rng.normal(p.proj, p.stdev, n))
    return total


def win_probability(mine: list[Player], theirs: list[Player], n: int = 10000, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    a, b = simulate(mine, n, rng), simulate(theirs, n, rng)
    return {
        "win_pct": float((a > b).mean()),
        "my_proj": float(sum(p.proj for p in mine)),
        "opp_proj": float(sum(p.proj for p in theirs)),
        "my_range": (float(np.percentile(a, 10)), float(np.percentile(a, 90))),
    }


def strategy_hint(win_pct: float) -> str:
    if win_pct >= 0.65:
        return "You're the favorite: favor high-floor starters and avoid risky boom/bust plays."
    if win_pct <= 0.40:
        return "You're the underdog: lean toward high-ceiling players; you need variance."
    return "Toss-up: take the higher projection, and break ties toward the better matchup."
