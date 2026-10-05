"""Pick the best legal lineup. Fixed slots take the top players at each
position, then FLEX takes the best remaining RB/WR/TE. For this slot layout
that greedy order is exactly optimal."""
from .leagues import FLEX_ELIGIBLE
from .models import Player


def optimize_lineup(roster: list[Player], starters: dict) -> tuple[list[Player], list[Player]]:
    pool = sorted((p for p in roster if p.available), key=lambda p: p.proj, reverse=True)
    lineup, used = [], set()
    for pos, n in starters.items():
        if pos == "FLEX":
            continue
        picks = [p for p in pool if p.pos == pos][:n]
        lineup += picks
        used.update(id(p) for p in picks)
    for _ in range(starters.get("FLEX", 0)):
        flex = next((p for p in pool if p.pos in FLEX_ELIGIBLE and id(p) not in used), None)
        if flex:
            lineup.append(flex)
            used.add(id(flex))
    bench = [p for p in roster if id(p) not in used]
    return lineup, bench


def lineup_changes(current: list[Player], optimal: list[Player]) -> list[str]:
    """Plain-English swap suggestions between the lineup you have set and the best one."""
    cur_ids, opt_ids = {p.name for p in current}, {p.name for p in optimal}
    outs = sorted((p for p in current if p.name not in opt_ids), key=lambda p: p.proj)
    ins = sorted((p for p in optimal if p.name not in cur_ids), key=lambda p: -p.proj)
    notes = []
    for out, inn in zip(outs, ins):
        why = f"{out.name} is {out.status}" if not out.available else f"+{inn.proj - out.proj:.1f} projected pts"
        notes.append(f"Start {inn.name} ({inn.pos}, {inn.proj:.1f}) over {out.name} ({out.proj:.1f}): {why}")
    return notes
