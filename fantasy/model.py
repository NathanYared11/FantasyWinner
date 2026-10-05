"""The projection model, shared by the backtest (fantasy.backtest) and the live pipeline so the thing
that is validated is exactly the thing that runs. Parameters live in fantasy/params.json (written by
the backtest); DEFAULTS apply until it has been run.
"""
import json
from collections import defaultdict
from pathlib import Path

PARAMS_PATH = Path(__file__).resolve().parent / "params.json"
POS = ("QB", "RB", "WR", "TE")
DEFAULT_PPG = {"QB": 14.0, "RB": 7.0, "WR": 7.0, "TE": 5.5, "K": 8.0, "D/ST": 7.0}
LEAGUE_AVG_IMPLIED = 22.5

DEFAULTS = {
    "blend": {"K": 4, "decay": .7, "mix": .6, "lam": 1.0, "usage": .3,
              "env": {"QB": .2, "RB": .2, "WR": 0, "TE": 0}, "wind": .95, "opp": {"QB": 0, "RB": 0, "WR": 0, "TE": 0},
              "bias": {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0}},
    "ratio_q": None,                 # per-position quantiles of actual/predicted (101 points, mean 1)
    "p_play_healthy": [.93],         # P(plays in week k | healthy now), non-bye weeks
    "p_play_by_status": {"Questionable": .71, "Doubtful": .02, "Out": 0.0},
    "p_play_after_out": [0, .33, .52, .63, .70],
}


def load_params():
    P = json.loads(json.dumps(DEFAULTS))
    if PARAMS_PATH.exists():
        saved = json.loads(PARAMS_PATH.read_text())
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(P.get(k), dict):
                P[k].update(v)
            else:
                P[k] = v
    return P


def predict_ppg(hist, prev, pos, snap, line, opp_rel, B):
    """Expected PPR points in one game, given only pre-game information.

    hist: this season's points in games played (oldest first); prev: last season's ppg or None;
    snap: this season's offense snap fractions (oldest first); line: (implied, opp_implied, windy) or None;
    opp_rel: opposing defense's points allowed to `pos` relative to league average (1.0 = average).
    """
    base = DEFAULT_PPG[pos]
    prior = base if prev is None else B["lam"] * prev + (1 - B["lam"]) * base * 1.4
    n = len(hist)
    if n:
        wts = [B["decay"] ** (n - 1 - i) for i in range(n)]
        recent = sum(v * w for v, w in zip(hist, wts)) / sum(wts)
        actual = B["mix"] * recent + (1 - B["mix"]) * (sum(hist) / n)
        mean = (n * actual + B["K"] * prior) / (n + B["K"])
    else:
        mean = prior
    if pos in POS:
        sn = [v for v in snap if v > 0]
        if len(sn) >= 3 and B["usage"]:
            recent_s, season_s = sum(sn[-2:]) / 2, sum(sn) / len(sn)
            if season_s >= .2:
                mean *= max(.92, min(1.08, 1 + B["usage"] * (recent_s / season_s - 1)))
        if line and B["env"].get(pos):
            f = (line[0] / LEAGUE_AVG_IMPLIED) ** B["env"][pos]
            if line[2] and pos in ("QB", "WR", "TE"):
                f *= B["wind"]
            mean *= max(.8, min(1.2, f))
        if opp_rel is not None and B["opp"].get(pos):
            mean *= max(.85, min(1.15, opp_rel ** B["opp"][pos]))
        mean *= B["bias"].get(pos, 1.0)
    return mean


class Matchups:
    """Points allowed to each position by each defense, week by week -> relative strength before week w."""

    def __init__(self, rows, games):
        """rows: iterable of (week, defense_team, pos, pts); games: iterable of (week, team) scheduled games."""
        self.allowed = defaultdict(float)
        self.weeks = defaultdict(set)
        for w, d, pos, v in rows:
            self.allowed[(w, d, pos)] += v
        for w, t in games:
            self.weeks[t].add(w)
        self.league = {}

    def _league_mean(self, w, pos):
        if (w, pos) not in self.league:
            teams = [t for t, ws in self.weeks.items() if w in ws]
            self.league[(w, pos)] = sum(self.allowed.get((w, t, pos), 0.0) for t in teams) / max(len(teams), 1)
        return self.league[(w, pos)]

    def rel(self, w, defense, pos, shrink=4):
        ws = [k for k in sorted(self.weeks[defense]) if k < w]
        if not ws:
            return 1.0
        mine = sum(self.allowed.get((k, defense, pos), 0.0) for k in ws)
        lg = sum(self._league_mean(k, pos) for k in ws)
        if lg <= 0:
            return 1.0
        raw = mine / lg
        return 1 + (raw - 1) * len(ws) / (len(ws) + shrink)


def p_play(P, status, k, healthy_streak_known=True):
    """P(player is available k weeks from now) from the backtested availability tables."""
    healthy = P["p_play_healthy"]
    h = healthy[min(k, len(healthy) - 1)]
    after_out = P["p_play_after_out"]
    if status in ("ACTIVE", "NORMAL", None):
        return h
    if status in ("QUESTIONABLE", "DAY_TO_DAY"):
        return P["p_play_by_status"].get("Questionable", .71) if k == 0 else h
    if status == "DOUBTFUL":
        return P["p_play_by_status"].get("Doubtful", .02) if k == 0 else after_out[min(k, len(after_out) - 1)]
    if status in ("OUT", "SUSPENSION"):
        return after_out[min(k, len(after_out) - 1)]
    if status == "INJURY_RESERVE":            # IR needs >= 4 weeks; shift the Out-return curve
        return 0.0 if k < 3 else after_out[min(k - 3, len(after_out) - 1)]
    return h
