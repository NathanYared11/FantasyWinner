"""Stage 3: Monte Carlo season simulation -> playoff / bye / final / title odds, plus what-if moves.

    python -m fantasy.simulate cuzff legoat [--sims 10000]

Model (every piece is an assumption, listed so it can be challenged):
  * Each starter's weekly score is lognormal with the player's blended mean/sd (analyze.project).
  * QB/WR/TE (and, weakly, RB) from the same NFL team share a weekly shock (correlated offenses).
  * Availability per week from injury status + a small baseline DNP rate; NFL bye weeks score zero.
  * Each sim-week every team starts its best available lineup by expected points.
  * The current week only simulates starters whose NFL game has not finished, on top of live points.
  * Regular season by the real schedule; seeding = wins then points scored (this league's rule);
    fixed (non-reseeded) playoff bracket, weeks 15-17.
  * Common random numbers: a what-if re-uses the same draws, so odds *differences* are far less
    noisy than the odds themselves.
"""
import math
import sys
import zlib
from collections import defaultdict

import numpy as np

from . import config as C
from . import model as M
from .analyze import FLEX_POS, prepare

REG_END_PLAYOFF_WEEKS = (15, 16, 17)
RHO = {"QB": .15, "WR": .15, "TE": .15, "RB": .05, "K": 0.0, "D/ST": 0.0}
PARAMS = M.load_params()
GRID = np.linspace(0, 1, 101)
CV_LOGN = {"K": .4, "D/ST": .6}      # unvalidated: no K/DST history in the backtest


def phi(z):
    """Standard normal CDF (Abramowitz-Stegun erf approximation, ~1e-7 accurate; numpy has no erf)."""
    x = np.abs(z) / math.sqrt(2)
    t = 1 / (1 + .3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - .284496736) * t + .254829592) * t * np.exp(-x * x)
    return .5 * (1 + np.sign(z) * y)


def outcome(pos, mean, u, z=None):
    """Score = mean * empirical (actual/projected) ratio at quantile u. K and D/ST fall back to a lognormal."""
    q = (PARAMS["ratio_q"] or {}).get(pos)
    if q:
        return mean * np.interp(u, GRID, q)
    cv = CV_LOGN.get(pos, .5)
    s2 = math.log(1 + cv * cv)
    return mean * np.exp(-s2 / 2 + math.sqrt(s2) * z)


class Sim:
    def __init__(self, name, sims=10000, seed=2026):
        self.name, self.S, self.seed = name, sims, seed
        self.snap = prepare(name)
        self.nfl = self.snap["_nfl"]
        st = self.snap["settings"]
        self.week = st["current_week"]
        self.slots = st["lineup_slots"]
        self.reg_end = st["schedule"]["matchupPeriodCount"]
        self.n_playoff = st["schedule"]["playoffTeamCount"]
        self.team_ids = [t["id"] for t in self.snap["teams"]]
        self.tidx = {t: i for i, t in enumerate(self.team_ids)}
        self.weeks = list(range(self.week, REG_END_PLAYOFF_WEEKS[-1] + 1))
        self.W = len(self.weeks)
        self._z, self._u, self._shock = {}, {}, {}
        self.cal = 1.0
        healthy = ("ACTIVE", "NORMAL", "QUESTIONABLE", "DAY_TO_DAY")
        self.repl = {}      # replacement level = 3rd-best healthy free agent, shaded 5% for waiver competition
        for pos in ("QB", "RB", "WR", "TE", "K", "D/ST"):
            top = sorted((p["raw_ppg"] for p in self.snap["free_agents"] if p["pos"] == pos and p["injury"] in healthy), reverse=True)
            self.repl[pos] = .95 * (top[2] if len(top) > 2 else C_DEFAULT[pos])
        self.players = {p["id"]: p for t in self.snap["teams"] for p in t["roster"]}
        self.players.update({p["id"]: p for p in self.snap["free_agents"]})

        # live points + completed results from the ESPN schedule
        self.live = defaultdict(float)
        self.base_pf = defaultdict(float)
        self.matchups = defaultdict(list)           # week -> [(home, away)]
        for g in self.snap["schedule"]:
            if "away" not in g or g["playoff"]:
                continue
            if g["week"] == self.week:
                self.live[g["home"]], self.live[g["away"]] = g["home_pts"] or 0, g["away_pts"] or 0
            if g["week"] < self.week:
                self.base_pf[g["home"]] += g["home_pts"] or 0
                self.base_pf[g["away"]] += g["away_pts"] or 0
            elif g["week"] <= self.reg_end:
                self.matchups[g["week"]].append((g["home"], g["away"]))

    # ---- common random numbers ---------------------------------------------------------------
    def z(self, pid):
        if pid not in self._z:
            rng = np.random.default_rng([self.seed, pid % 2**32])
            self._z[pid] = rng.standard_normal((self.S, self.W), dtype=np.float32)
        return self._z[pid]

    def u(self, pid):
        if pid not in self._u:
            rng = np.random.default_rng([self.seed, 1, pid % 2**32])
            self._u[pid] = rng.random((self.S, self.W), dtype=np.float32)
        return self._u[pid]

    def shock(self, nfl_team):
        if nfl_team not in self._shock:
            rng = np.random.default_rng([self.seed, 2, zlib.crc32(nfl_team.encode())])
            self._shock[nfl_team] = rng.standard_normal((self.S, self.W), dtype=np.float32)
        return self._shock[nfl_team]

    # ---- one team, one week ----------------------------------------------------------------------
    def draws(self, plist, w):
        """(S, P) simulated scores and availability for players in week w."""
        j, k = self.weeks.index(w), w - self.week
        X = np.zeros((self.S, len(plist)), dtype=np.float32)
        A = np.zeros((self.S, len(plist)), dtype=bool)
        means = np.zeros(len(plist))
        for c, p in enumerate(plist):
            if p["bye"] == w:
                continue
            env = self.nfl.env_factor(p["pos"], p["nfl_team"], w) * self.nfl.opp_factor(p["pos"], p["nfl_team"], w)
            m = max(p["raw_ppg"] * env * self.cal, .5)
            rho = RHO.get(p["pos"], 0)
            zz = math.sqrt(rho) * self.shock(p["nfl_team"])[:, j] + math.sqrt(1 - rho) * self.z(p["id"])[:, j]
            X[:, c] = outcome(p["pos"], m, phi(zz), zz)
            A[:, c] = self.u(p["id"])[:, j] < M.p_play(PARAMS, p["injury"], k)
            means[c] = m
        return X, A, means

    def team_week(self, tid, plist, w):
        """Simulated team score for week w (S,)."""
        if w == self.week:   # only players still to play, in the lineup ESPN currently shows
            pend = [p for p in plist if p["slot"] not in (None, "BE", "IR")
                    and (g := self.nfl.game(w, p["nfl_team"])) and not g["done"]]
            if not pend:
                return np.full(self.S, self.live[tid], dtype=np.float32)
            X, A, _ = self.draws(pend, w)
            return self.live[tid] + (X * A).sum(1)
        X, A, means = self.draws(plist, w)
        sel = np.zeros_like(A)
        pos = [p["pos"] for p in plist]
        for ps in ("QB", "RB", "WR", "TE", "K", "D/ST"):
            k = self.slots.get(ps, 0)
            idx = sorted([i for i, x in enumerate(pos) if x == ps], key=lambda i: -means[i])
            if k and idx:
                sub = A[:, idx]
                sel[:, idx] = sub & (np.cumsum(sub, 1) <= k)
        kf = self.slots.get("FLEX", 0)
        fidx = sorted([i for i, x in enumerate(pos) if x in FLEX_POS], key=lambda i: -means[i])
        if kf and fidx:
            sub = A[:, fidx] & ~sel[:, fidx]
            sel[:, fidx] |= sub & (np.cumsum(sub, 1) <= kf)
        score = (X * sel).sum(1)
        # An empty slot (bye, injury, thin roster) is filled from waivers at replacement level.
        rng = np.random.default_rng([self.seed, 3, tid, self.weeks.index(w)])
        for ps in ("QB", "RB", "WR", "TE", "K", "D/ST"):
            filled = sum(sel[:, i] for i, x in enumerate(pos) if x == ps) if ps in pos else 0
            miss = self.slots.get(ps, 0) - filled
            score = score + self._fill(rng, ps, miss)
        if kf:
            filled = sum(sel[:, i] for i in fidx) if fidx else 0
            score = score + self._fill(rng, "WR", kf - filled)
        return score

    def _fill(self, rng, ps, miss):
        """Replacement-level scores for `miss` (S,) empty slots at position ps."""
        if np.isscalar(miss) and miss <= 0:
            return 0.0
        out = np.zeros(self.S, dtype=np.float32)
        for i in range(int(np.max(miss)) if not np.isscalar(miss) else int(miss)):
            draw = outcome(ps, self.repl[ps] * self.cal, rng.random(self.S), rng.standard_normal(self.S))
            out += np.where(miss > i, draw, 0).astype(np.float32)
        return out

    def calibrate(self):
        """Pull the league scoring level halfway toward what teams actually scored (3 weeks is noisy,
        so a full correction would overfit). Relative team strength is untouched."""
        done = [g for g in self.snap["schedule"] if g["week"] < self.week and "away" in g and not g["playoff"]]
        actual = sum((g["home_pts"] or 0) + (g["away_pts"] or 0) for g in done) / max(2 * len(done), 1)
        if not actual:
            return 1.0
        res = self.run()
        simmed = sum(o["avg_weekly"] for o in res.values()) / len(res)
        self.cal = 1 + .5 * (actual / simmed - 1)
        self.calibration = {"actual_mean": round(actual, 1), "sim_mean_before": round(simmed, 1), "scale": round(self.cal, 3)}
        return self.cal

    # ---- full season ----------------------------------------------------------------------------
    def run(self, rosters=None):
        """rosters: optional {team_id: [player dicts]} overriding the current rosters."""
        S, T = self.S, len(self.team_ids)
        rosters = {t["id"]: t["roster"] for t in self.snap["teams"]} | (rosters or {})
        wins = np.tile(np.array([t["wins"] + .5 * t["ties"] for t in self.snap["teams"]], dtype=np.float32), (S, 1))
        pf = np.tile(np.array([self.base_pf[t] for t in self.team_ids], dtype=np.float32), (S, 1))
        scores = {}
        for w in self.weeks:
            scores[w] = np.stack([self.team_week(t, rosters[t], w) for t in self.team_ids], 1)
        for w in self.weeks:
            if w <= self.reg_end:
                pf += scores[w]
                for h, a in self.matchups[w]:
                    hi, ai = self.tidx[h], self.tidx[a]
                    hw = scores[w][:, hi] > scores[w][:, ai]
                    wins[:, hi] += hw
                    wins[:, ai] += ~hw
        order = np.argsort(-(wins * 1e6 + pf), axis=1, kind="stable")     # seed s -> team index
        N = self.n_playoff
        rows = np.arange(S)

        def play(w, a, b):    # a is the higher seed; ties go to a
            sa, sb = scores[w][rows, a], scores[w][rows, b]
            return np.where(sa >= sb, a, b)

        seed = lambda s: order[:, s - 1]
        w1, w2, w3 = REG_END_PLAYOFF_WEEKS
        if N == 6:
            a, b = play(w1, seed(3), seed(6)), play(w1, seed(4), seed(5))
            f1, f2 = play(w2, seed(1), b), play(w2, seed(2), a)
            byes = (1, 2)
        elif N == 7:
            a, b, c = play(w1, seed(2), seed(7)), play(w1, seed(3), seed(6)), play(w1, seed(4), seed(5))
            f1, f2 = play(w2, seed(1), c), play(w2, a, b)
            byes = (1,)
        else:
            raise NotImplementedError(f"{N}-team playoff bracket")
        champ = play(w3, f1, f2) if True else None
        out = {}
        for t, i in self.tidx.items():
            in_po = (order[:, :N] == i).any(1)
            out[t] = {"playoffs": in_po.mean(), "bye": (order[:, [b - 1 for b in byes]] == i).any(1).mean(),
                      "final": ((f1 == i) | (f2 == i)).mean(), "title": (champ == i).mean(),
                      "avg_wins": float(wins[:, i].mean()), "avg_weekly": float(np.mean([scores[w][:, i].mean() for w in self.weeks if w > self.week]))}
        return out


def with_move(sim, team_id, add=(), drop=()):
    """Roster list for team_id after adding/dropping player ids (adds are free agents or other-team players)."""
    cur = [p for p in sim.snap["teams"][sim.tidx[team_id]]["roster"] if p["id"] not in set(drop)]
    new = []
    for pid in add:
        p = dict(sim.players[pid])
        p["slot"] = None
        new.append(p)
    return {team_id: cur + new}


def fmt(o):
    return f'{o["playoffs"]*100:5.1f}% {o["bye"]*100:5.1f}% {o["final"]*100:5.1f}% {o["title"]*100:5.1f}%'


def odds_table(sim, res):
    me = sim.snap["my_team_id"]
    names = {t["id"]: t["name"] for t in sim.snap["teams"]}
    L = [f'## {sim.snap["settings"]["name"]} — odds ({sim.S:,} sims, week {sim.week}; ESPN {sim.snap["refreshed_at"]}, nflverse {sim.snap["nfl_refreshed_at"]})', "",
         "| Team | Rec | Playoffs | Bye | Final | **Title** | Avg wins |", "|--|--|--|--|--|--|--|"]
    recs = {t["id"]: f'{t["wins"]}-{t["losses"]}' for t in sim.snap["teams"]}
    for t, o in sorted(res.items(), key=lambda kv: -kv[1]["title"]):
        L.append(f'| {names[t]}{" **(me)**" if t == me else ""} | {recs[t]} | {o["playoffs"]*100:.1f}% | {o["bye"]*100:.1f}% | '
                 f'{o["final"]*100:.1f}% | **{o["title"]*100:.1f}%** | {o["avg_wins"]:.1f} |')
    if getattr(sim, "calibration", None):
        c = sim.calibration
        L += ["", f'_Scoring calibration: teams averaged {c["actual_mean"]} so far, uncalibrated model {c["sim_mean_before"]}; means scaled by {c["scale"]}._']
    return "\n".join(L)


def waiver_scan(sim, base, top=6):
    """Title-odds change from each best-available free agent, dropping my lowest-value bench player."""
    me = sim.snap["my_team_id"]
    roster = sim.snap["teams"][sim.tidx[me]]["roster"]
    bench = sorted([p for p in roster if p["slot"] in ("BE",) and p["pos"] in ("QB", "RB", "WR", "TE")], key=lambda p: p["ppg"])
    if not bench:
        return []
    drop = bench[0]
    healthy = ("ACTIVE", "NORMAL", "QUESTIONABLE", "DAY_TO_DAY")
    cands = []
    for pos in ("QB", "RB", "WR", "TE"):
        cands += sorted([p for p in sim.snap["free_agents"] if p["pos"] == pos and p["injury"] in healthy], key=lambda p: -p["ppg"])[:3]
    rows = []
    for p in cands:
        r = sim.run(with_move(sim, me, add=[p["id"]], drop=[drop["id"]]))[me]
        rows.append({"add": f'{p["name"]} ({p["pos"]}, {p["ppg"]:.1f})', "drop": drop["name"],
                     "d_playoffs": r["playoffs"] - base[me]["playoffs"], "d_title": r["title"] - base[me]["title"]})
    return sorted(rows, key=lambda r: -r["d_title"])[:top]


def main(argv):
    sims = 10000
    if "--sims" in argv:
        i = argv.index("--sims")
        sims = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    for lg in argv or C.LEAGUES:
        sim = Sim(lg, sims)
        sim.calibrate()
        res = sim.run()
        text = odds_table(sim, res)
        me = sim.snap["my_team_id"]
        text += "\n\n### Waiver what-ifs for my team (drop my lowest bench player; common random numbers)\n\n| Add | Drop | Δ playoffs | Δ title |\n|--|--|--|--|\n"
        for r in waiver_scan(sim, res):
            text += f'| {r["add"]} | {r["drop"]} | {r["d_playoffs"]*100:+.1f} pts | {r["d_title"]*100:+.2f} pts |\n'
        (C.DATA_DIR / lg / "odds.md").write_text(text)
        print(text, "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
