"""Simulate the rest of the regular season for playoff and bye odds."""
import numpy as np

from .leagues import League


def simulate_season(teams: dict, schedule: list, league: League, n: int = 4000, seed: int = 11,
                    force: tuple | None = None) -> dict:
    """teams: name -> {"wins", "pf", "mean", "sd"}; schedule: list of weeks, each a
    list of (team_a, team_b) matchups still to play. force=(team, True/False) fixes
    that team's next result, to measure how much one game swings the odds."""
    rng = np.random.default_rng(seed)
    names = list(teams)
    idx = {t: i for i, t in enumerate(names)}
    wins = np.tile(np.array([teams[t]["wins"] for t in names], float), (n, 1))
    pf = np.tile(np.array([teams[t]["pf"] for t in names], float), (n, 1))
    forced_done = False
    for week in schedule:
        for a, b in week:
            sa = rng.normal(teams[a]["mean"], teams[a]["sd"], n)
            sb = rng.normal(teams[b]["mean"], teams[b]["sd"], n)
            a_wins = sa > sb
            if force and not forced_done and force[0] in (a, b):
                a_wins = np.full(n, force[1] if force[0] == a else not force[1])
                forced_done = True
            wins[:, idx[a]] += a_wins
            wins[:, idx[b]] += ~a_wins
            pf[:, idx[a]] += sa
            pf[:, idx[b]] += sb
    order = np.argsort(-(wins * 1e6 + pf), axis=1)  # tiebreaker: total points for
    rank = np.empty_like(order)
    rows = np.arange(n)[:, None]
    rank[rows, order] = np.arange(len(names))[None, :]
    return {
        t: {"playoff": float((rank[:, i] < league.playoff_teams).mean()),
            "bye": float((rank[:, i] < league.byes).mean()),
            "avg_wins": float(wins[:, i].mean())}
        for t, i in idx.items()
    }


def round_robin(names: list, weeks: int) -> list:
    """Circle-method schedule, repeating if more weeks than a full round."""
    names = list(names)
    if len(names) % 2:
        names.append(None)
    n, rounds = len(names), []
    for _ in range(n - 1):
        rounds.append([(names[i], names[n - 1 - i]) for i in range(n // 2)
                       if names[i] is not None and names[n - 1 - i] is not None])
        names = [names[0], names[-1]] + names[1:-1]
    return [rounds[w % len(rounds)] for w in range(weeks)]
