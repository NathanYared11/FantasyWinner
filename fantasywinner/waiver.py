"""Rank free agents by how much they'd actually improve your lineup."""
from .leagues import League
from .models import Player
from .optimizer import optimize_lineup


def lineup_total(roster: list[Player], starters: dict) -> float:
    return sum(p.proj for p in optimize_lineup(roster, starters)[0])


def waiver_targets(roster: list[Player], free_agents: list[Player], league: League, top: int = 15) -> list[dict]:
    base = lineup_total(roster, league.starters)
    best_lineup, _ = optimize_lineup(roster, league.starters)
    in_lineup = {p.name for p in best_lineup}
    counts = {}
    for p in roster:
        counts[p.pos] = counts.get(p.pos, 0) + 1
    out = []
    for fa in free_agents:
        if not fa.available:
            continue
        best = None
        for drop in roster:
            # Only bench players are drop candidates, unless they're unavailable.
            if drop.name in in_lineup and drop.available:
                continue
            if counts.get(fa.pos, 0) >= league.max_per_pos.get(fa.pos, 99) and drop.pos != fa.pos:
                continue  # would break the position maximum
            new = [p for p in roster if p.name != drop.name] + [fa]
            gain = lineup_total(new, league.starters) - base
            key = (gain, -drop.proj)
            if best is None or key > best[0]:
                best = (key, drop, gain)
        if best is None:
            continue
        _, drop, gain = best
        out.append({"add": fa, "drop": drop, "gain": round(gain, 1),
                    "depth": round(fa.proj - drop.proj, 1), "advice": claim_advice(gain, fa, league)})
    out.sort(key=lambda r: (r["gain"], r["depth"] + r["add"].trend * 0.05), reverse=True)
    return out[:top]


def claim_advice(gain: float, fa: Player, league: League) -> str:
    if gain >= 3:
        return "Must claim: clear lineup upgrade" if league.key != "cuzff" else \
               "Worth burning waiver priority: clear lineup upgrade"
    if gain > 0.5:
        return "Good claim" if league.key != "cuzff" else "Only claim if priority is high; modest upgrade"
    if fa.trend >= 20:
        return "Stash: trending up fast" if league.key != "cuzff" else "Stash only if you have a spare spot; not worth priority"
    return "Skip"
