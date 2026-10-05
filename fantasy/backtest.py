"""Projection backtest + tuning on past seasons (nflverse PPR points, matches both leagues' scoring).

    python -m fantasy.backtest

For every (player, week >= 4) it predicts that week's PPR points using ONLY information available
before the game: earlier weeks, the prior season, snap trends, that week's Vegas line and the
opposing defense's record against the position. It tunes on 2024, reports on the untouched 2025
season, then refits on both and writes fantasy/params.json (used by the live pipeline).
"""
import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import model as M
from . import nfl

NFLV = nfl.DIR
POS = M.POS
REL = {"QB": 14.0, "RB": 8.0, "WR": 8.0, "TE": 6.5}      # fantasy-relevant: rosterable players only
YEARS = (2022, 2023, 2024, 2025)


def fetch_history():
    for y in YEARS:
        for rel in (f"stats_player/stats_player_week_{y}.csv", f"injuries/injuries_{y}.csv", f"snap_counts/snap_counts_{y}.csv"):
            f = NFLV / Path(rel).name
            if not f.exists():
                subprocess.run(["curl", "-sS", "-m", "180", "-L", "--fail", "-o", str(f), f"{nfl.BASE}/{rel}"], check=True)


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class History:
    def __init__(self):
        fetch_history()
        pfr = {r["pfr_id"]: r["gsis_id"] for r in read(NFLV / "players.csv") if r["pfr_id"]}
        self.pts = defaultdict(lambda: defaultdict(dict))        # season -> gid -> week -> ppr pts
        self.pos, self.team = {}, {}
        self.snap = defaultdict(lambda: defaultdict(dict))
        for y in YEARS:
            for r in read(NFLV / f"stats_player_week_{y}.csv"):
                if r["season_type"] == "REG" and r["position"] in POS:
                    self.pts[y][r["player_id"]][int(r["week"])] = float(r["fantasy_points_ppr"] or 0)
                    self.pos[r["player_id"]] = r["position"]
                    self.team[(y, r["player_id"], int(r["week"]))] = r["team"]
            for r in read(NFLV / f"snap_counts_{y}.csv"):
                g = pfr.get(r["pfr_player_id"])
                if g and r["game_type"] == "REG" and r["offense_pct"] not in ("", None):
                    self.snap[y][g][int(r["week"])] = float(r["offense_pct"])      # fraction 0-1
        self.lines, self.opp = {}, {}
        self.team_weeks = defaultdict(set)
        games = defaultdict(list)
        for r in read(NFLV / "games.csv"):
            if r["game_type"] != "REG":
                continue
            y, wk = int(r["season"]), int(r["week"])
            h, a = r["home_team"], r["away_team"]
            self.opp[(y, wk, h)], self.opp[(y, wk, a)] = a, h
            self.team_weeks[(y, h)].add(wk)
            self.team_weeks[(y, a)].add(wk)
            games[y] += [(wk, h), (wk, a)]
            if r["spread_line"] and r["total_line"]:
                sp, tot = float(r["spread_line"]), float(r["total_line"])
                windy = r["roof"] == "outdoors" and r["wind"] != "" and float(r["wind"]) >= 15
                self.lines[(y, wk, h)] = (tot / 2 + sp / 2, tot / 2 - sp / 2, windy)
                self.lines[(y, wk, a)] = (tot / 2 - sp / 2, tot / 2 + sp / 2, windy)
        self.matchups = {}
        for y in YEARS:
            rows = []
            for gid, wk in self.pts[y].items():
                for w, v in wk.items():
                    d = self.opp.get((y, w, self.team.get((y, gid, w))))
                    if d:
                        rows.append((w, d, self.pos[gid], v))
            self.matchups[y] = M.Matchups(rows, games[y])


def build_rows(h, season, first_week=4, last_week=17):
    """One row per (player, week) actually played, carrying only pre-game information."""
    rows = []
    for gid, wk_pts in h.pts[season].items():
        pos = h.pos[gid]
        prev = [v for _, v in sorted(h.pts[season - 1].get(gid, {}).items())]
        ppg_prev = sum(prev) / len(prev) if len(prev) >= 4 else None
        for w in range(first_week, last_week + 1):
            if w not in wk_pts:
                continue
            hist = [v for k, v in sorted(wk_pts.items()) if k < w]
            if not hist and ppg_prev is None:
                continue
            if max(ppg_prev or 0, sum(hist) / len(hist) if hist else 0) < REL[pos]:
                continue
            team = h.team.get((season, gid, w))
            d = h.opp.get((season, w, team))
            future = [wk_pts[k] for k in range(w, min(w + 4, last_week + 1)) if k in wk_pts]
            rows.append({"gid": gid, "pos": pos, "w": w, "season": season, "actual": wk_pts[w], "hist": hist, "prev": ppg_prev,
                         "snap": [v for k, v in sorted(h.snap[season].get(gid, {}).items()) if k < w],
                         "line": h.lines.get((season, w, team)),
                         "opp_rel": h.matchups[season].rel(w, d, pos) if d else None, "ros4": sum(future) / len(future)})
    return rows


def predict(r, B):
    return M.predict_ppg(r["hist"], r["prev"], r["pos"], r["snap"], r["line"], r["opp_rel"], B)


def metrics(rows, pred_fn, spearman=False):
    pred = np.array([pred_fn(r) for r in rows])
    act = np.array([r["actual"] for r in rows])
    ros = np.array([r["ros4"] for r in rows])
    out = {"rmse": float(np.sqrt(np.mean((pred - act) ** 2))), "mae": float(np.mean(np.abs(pred - act))),
           "bias": float(np.mean(pred - act)), "rmse_ros4": float(np.sqrt(np.mean((pred - ros) ** 2)))}
    if spearman:
        by = defaultdict(list)
        for r, p in zip(rows, pred):
            by[(r["season"], r["w"], r["pos"])].append((p, r["actual"]))
        rs = []
        for v in by.values():
            if len(v) >= 8:
                a, b = np.array([x[0] for x in v]).argsort().argsort(), np.array([x[1] for x in v]).argsort().argsort()
                rs.append(np.corrcoef(a, b)[0, 1])
        out["rank_corr"] = float(np.mean(rs))
    return out


def baseline_fn(kind):
    def f(r):
        d = M.DEFAULT_PPG[r["pos"]]
        if kind == "season_avg":
            return sum(r["hist"]) / len(r["hist"]) if r["hist"] else (r["prev"] or d)
        if kind == "last3":
            return sum(r["hist"][-3:]) / len(r["hist"][-3:]) if r["hist"] else (r["prev"] or d)
        return r["prev"] if r["prev"] is not None else d
    return f


def objective(rows, B, ref):
    s = metrics(rows, lambda r: predict(r, B))
    return .5 * s["rmse"] / ref["rmse"] + .5 * s["rmse_ros4"] / ref["rmse_ros4"]


def tune(rows):
    """Coordinate descent on the blend; objective = mean relative RMSE (this week, next-4-week avg) vs season-avg."""
    ref = metrics(rows, baseline_fn("season_avg"))
    best = json.loads(json.dumps(M.DEFAULTS["blend"]))
    best_obj = objective(rows, best, ref)
    scalar = [("K", [0, 1, 2, 3, 4, 6, 8, 12]), ("decay", [.4, .5, .6, .7, .8, .9, 1.0]), ("mix", [0, .3, .6, .8, 1.0]),
              ("lam", [.5, .7, .85, 1.0]), ("usage", [0, .15, .3, .5, .8]), ("wind", [1.0, .97, .94, .9])]
    per_pos = [("env", (0, .2, .4, .6, .8, 1.0)), ("opp", (0, .3, .6, 1.0, 1.5, 2.0))]
    for _ in range(2):
        for key, vals in scalar:
            for v in vals:
                cand = dict(best, **{key: v})
                o = objective(rows, cand, ref)
                if o < best_obj - 1e-9:
                    best, best_obj = cand, o
        for key, vals in per_pos:
            for pos in POS:
                for v in vals:
                    cand = dict(best, **{key: dict(best[key], **{pos: v})})
                    o = objective(rows, cand, ref)
                    if o < best_obj - 1e-9:
                        best, best_obj = cand, o
    return best, best_obj


def bias_and_ratios(rows, B):
    """Per-position bias correction and the empirical distribution of actual/predicted (mean 1)."""
    bias, ratio_q, cov = {}, {}, {}
    B = json.loads(json.dumps(B))
    for pos in POS:
        rs = [r for r in rows if r["pos"] == pos]
        pred = np.array([predict(r, B) for r in rs])
        act = np.array([r["actual"] for r in rs])
        bias[pos] = float(act.sum() / pred.sum())
        ratio = act / np.maximum(pred * bias[pos], .5)
        ratio = ratio / ratio.mean()
        q = np.quantile(ratio, np.linspace(0, 1, 101))
        ratio_q[pos] = [round(float(x), 4) for x in q]
        cov[pos] = {"p10": round(float(q[10]), 2), "p50": round(float(q[50]), 2), "p90": round(float(q[90]), 2),
                    "sd_over_mean": round(float(ratio.std()), 3), "n": len(rs)}
    return bias, ratio_q, cov


def availability(h):
    """P(plays k weeks ahead | healthy and played now), by non-bye week; plus status tables."""
    healthy = defaultdict(lambda: [0, 0])
    by_status, after_out = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for y in (2023, 2024, 2025):
        relevant = {g for g, wk in h.pts[y].items() if wk and sum(wk.values()) / len(wk) >= REL[h.pos[g]]}
        status = {}
        for r in read(NFLV / f"injuries_{y}.csv"):
            if r["game_type"] == "REG" and r["gsis_id"] in relevant:
                status[(r["gsis_id"], int(r["week"]))] = r["report_status"] or "None"
        for g in relevant:
            known = sorted(w for w in h.pts[y][g])
            for w in range(2, 18):
                near = min(known, key=lambda k: abs(k - w))            # team on a nearby week he played
                team = h.team.get((y, g, near))
                tw = h.team_weeks[(y, team)] if team else set()
                s = status.get((g, w), "Not listed")
                if w in tw:                                    # status table: only weeks the team plays
                    by_status[s][0] += w in h.pts[y][g]
                    by_status[s][1] += 1
                if w in h.pts[y][g] and s in ("Not listed", "None"):           # healthy-and-played now
                    for k in range(1, 12):
                        if w + k <= 17 and (w + k) in tw:
                            healthy[k][0] += (w + k) in h.pts[y][g]
                            healthy[k][1] += 1
                if s == "Out":
                    for k in range(1, 7):
                        if w + k <= 17 and (w + k) in tw:
                            after_out[k][0] += (w + k) in h.pts[y][g]
                            after_out[k][1] += 1
    rate = lambda d: {k: v[0] / v[1] for k, v in sorted(d.items(), key=lambda kv: str(kv[0])) if v[1]}
    return rate(healthy), rate(by_status), rate(after_out), {k: v[1] for k, v in by_status.items()}


def fmt(s):
    return (f'RMSE {s["rmse"]:.2f} | MAE {s["mae"]:.2f} | bias {s["bias"]:+.2f} | RMSE vs next-4-wk avg {s["rmse_ros4"]:.2f}'
            + (f' | weekly rank-corr {s["rank_corr"]:.3f}' if "rank_corr" in s else ""))


def main():
    h = History()
    train, test = build_rows(h, 2024), build_rows(h, 2025)
    L = ["# Projection backtest (nflverse PPR; fantasy-relevant players, weeks 4-17)", "",
         f"Tuned on 2024 ({len(train)} player-weeks); reported on held-out 2025 ({len(test)} player-weeks).", ""]
    tuned, _ = tune(train)
    L.append("## Held-out 2025")
    for label, fn in (("season-to-date avg (baseline)", baseline_fn("season_avg")), ("last-3 avg (baseline)", baseline_fn("last3")),
                      ("prior-year ppg (baseline)", baseline_fn("prior")), ("**my blend (tuned on 2024)**", lambda r: predict(r, tuned))):
        L.append(f"- {label}: {fmt(metrics(test, fn, spearman=True))}")
    L += ["", "## Ablations on 2025 (tuned blend, one piece removed)"]
    for label, mod in (("usage trend off", {"usage": 0}), ("game environment off", {"env": {p: 0 for p in POS}}),
                       ("wind off", {"wind": 1.0}), ("opponent matchup off", {"opp": {p: 0 for p in POS}}),
                       ("prior season off", {"K": 0})):
        L.append(f"- {label}: {fmt(metrics(test, lambda r: predict(r, dict(tuned, **mod))))}")
    final, _ = tune(train + test)
    bias, ratio_q, cov = bias_and_ratios(train + test, final)
    final["bias"] = {p: round(v, 4) for p, v in bias.items()}
    healthy, by_status, after_out, n_status = availability(h)
    L += ["", "## Final blend (refit on 2024+2025)", "", "```json", json.dumps(final, indent=1), "```", "",
          "## Outcome distribution: actual / predicted, per position (empirical, drives floor/ceiling and the simulation)", ""]
    for pos, c in cov.items():
        L.append(f'- {pos}: P10 {c["p10"]}x, median {c["p50"]}x, P90 {c["p90"]}x of projection; sd/mean {c["sd_over_mean"]} (n={c["n"]})')
    L += ["", "## Availability, relevant players 2023-25 (non-bye weeks)", "",
          "P(plays) by injury-report status that week: " + ", ".join(f"{s} {v*100:.0f}% (n={n_status[s]})" for s, v in by_status.items() if n_status[s] >= 30),
          "", "P(plays k weeks ahead | healthy and played now): " + ", ".join(f"k={k}: {v*100:.0f}%" for k, v in healthy.items()),
          "", "P(plays k weeks ahead | listed Out now): " + ", ".join(f"k={k}: {v*100:.0f}%" for k, v in after_out.items())]
    (M.PARAMS_PATH).write_text(json.dumps({
        "blend": final, "ratio_q": ratio_q,
        "p_play_healthy": [round(healthy[1], 3)] + [round(healthy[k], 3) for k in sorted(healthy)],
        "p_play_by_status": {"Questionable": round(by_status.get("Questionable", .71), 3), "Doubtful": round(by_status.get("Doubtful", .02), 3)},
        "p_play_after_out": [0.0] + [round(after_out[k], 3) for k in sorted(after_out)]}, indent=1))
    text = "\n".join(L)
    (nfl.DIR.parent / "backtest.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
