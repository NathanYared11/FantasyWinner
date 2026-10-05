"""Fictional demo rosters so the dashboard works before ESPN is connected."""
from .models import Player

_ROWS = [
    # name, pos, team, proj, status, opp, slot
    ("Demo QB Alpha", "QB", "AAA", 21.5, "ACTIVE", "vs BBB", "QB"),
    ("Demo QB Backup", "QB", "CCC", 15.0, "ACTIVE", "@ DDD", "BE"),
    ("Demo RB One", "RB", "EEE", 17.2, "ACTIVE", "vs FFF", "RB"),
    ("Demo RB Two", "RB", "GGG", 9.1, "QUESTIONABLE", "@ HHH", "RB"),
    ("Demo RB Three", "RB", "III", 12.8, "ACTIVE", "vs JJJ", "BE"),
    ("Demo RB Four", "RB", "KKK", 7.0, "ACTIVE", "@ LLL", "BE"),
    ("Demo WR One", "WR", "MMM", 16.4, "ACTIVE", "vs NNN", "WR"),
    ("Demo WR Two", "WR", "OOO", 8.0, "OUT", "@ PPP", "WR"),
    ("Demo WR Three", "WR", "QQQ", 13.9, "ACTIVE", "vs RRR", "FLEX"),
    ("Demo WR Four", "WR", "SSS", 12.1, "ACTIVE", "@ TTT", "BE"),
    ("Demo TE One", "TE", "UUU", 11.3, "ACTIVE", "vs VVV", "TE"),
    ("Demo K One", "K", "WWW", 8.2, "ACTIVE", "@ XXX", "K"),
    ("Demo DST One", "DST", "YYY", 7.5, "ACTIVE", "vs ZZZ", "DST"),
]

_OPP = [
    ("Opp QB", "QB", 19.0, "QB"), ("Opp RB A", "RB", 15.0, "RB"), ("Opp RB B", "RB", 11.0, "RB"),
    ("Opp WR A", "WR", 15.5, "WR"), ("Opp WR B", "WR", 12.0, "WR"), ("Opp TE", "TE", 9.0, "TE"),
    ("Opp FLEX", "WR", 11.5, "FLEX"), ("Opp K", "K", 7.8, "K"), ("Opp DST", "DST", 8.0, "DST"),
]


def sample_roster() -> list[Player]:
    return [Player(n, pos, t, pr, st, o, slot=sl) for n, pos, t, pr, st, o, sl in _ROWS]


def sample_opponent() -> list[Player]:
    return [Player(n, pos, "OPP", pr, slot=sl) for n, pos, pr, sl in _OPP]


# ---- fictional league for demo mode ----------------------------------------
import numpy as np

from .season import round_robin

_COUNTS = {"QB": 2, "RB": 5, "WR": 5, "TE": 2, "K": 1, "DST": 1}
_RANGE = {"QB": (13, 23), "RB": (5, 18), "WR": (5, 17), "TE": (3.5, 12), "K": (6, 9), "DST": (5, 9)}
_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1}


def sample_league(n_teams: int = 12, seed: int = 3) -> dict:
    """Team name -> roster. Team 'You' is the sample_roster() above."""
    rng = np.random.default_rng(seed)
    league = {"You": sample_roster()}
    for t in range(2, n_teams + 1):
        roster = []
        need = {pos: float(rng.uniform(0.65, 1.3)) for pos in _COUNTS}  # each team is strong/weak at different spots
        for pos, n in _COUNTS.items():
            lo, hi = _RANGE[pos]
            for i in range(n):
                proj = float(rng.uniform(lo, hi)) * need[pos] * (1.0 if i < _STARTERS.get(pos, 1) + 1 else 0.7)
                roster.append(Player(f"T{t} {pos}{i + 1}", pos, "DEM", round(proj, 1)))
        league[f"Team {t}"] = roster
    return league


def sample_free_agents(seed: int = 5) -> list[Player]:
    rng = np.random.default_rng(seed)
    fa = []
    for pos, n in (("QB", 3), ("RB", 8), ("WR", 8), ("TE", 4), ("K", 3), ("DST", 3)):
        lo, hi = _RANGE[pos]
        for i in range(n):
            fa.append(Player(f"FA {pos}{i + 1}", pos, "FAG", round(float(rng.uniform(lo * 0.5, hi * 0.8)), 1),
                             trend=round(float(rng.uniform(-5, 45)), 1)))
    return fa


def sample_season(current_week: int = 4, regular_weeks: int = 14, seed: int = 9):
    """Teams (with records so far) and the schedule still to play."""
    rng = np.random.default_rng(seed)
    league = sample_league()
    names = list(league)
    strength = {t: sum(p.proj for p in __import__("fantasywinner.optimizer", fromlist=["x"]).optimize_lineup(
        league[t], _STARTERS_FULL)[0]) for t in names}
    teams = {t: {"wins": 0, "pf": 0.0, "mean": strength[t], "sd": 22.0} for t in names}
    sched = round_robin(names, regular_weeks)
    for week in sched[: current_week - 1]:
        for a, b in week:
            sa, sb = rng.normal(teams[a]["mean"], 22), rng.normal(teams[b]["mean"], 22)
            teams[a]["pf"] += sa
            teams[b]["pf"] += sb
            teams[a if sa > sb else b]["wins"] += 1
    return teams, sched[current_week - 1:]


_STARTERS_FULL = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1}
