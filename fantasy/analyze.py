"""Stage 2: league-wide analysis from a snapshot written by fantasy.ingest.

    python -m fantasy.analyze cuzff legoat

Writes data/<league>/analysis.json and data/<league>/report.md.

Everything here is a model with stated assumptions, not ESPN's numbers: projections blend recent
production, season-to-date and ESPN's preseason projection; probabilities and scores are heuristics.
"""
import json
import math
import statistics as stats
import sys
from pathlib import Path

from . import config as C

DATA = Path(__file__).resolve().parent.parent / "data"

# Assumptions (all tunable) ---------------------------------------------------------------------
K_PRIOR = 4                      # weeks of evidence worth the preseason prior
RECENCY = 0.7                    # per-week decay for recent form
CV = {"QB": .35, "RB": .50, "WR": .55, "TE": .60, "K": .40, "D/ST": .60}   # weekly sd / mean prior
DEFAULT_PPG = {"QB": 12, "RB": 6, "WR": 6, "TE": 5, "K": 7, "D/ST": 6}
# Rest-of-season availability by injury designation (fraction of expected output retained).
HEALTH = {"ACTIVE": 1.0, "NORMAL": 1.0, "QUESTIONABLE": .95, "DAY_TO_DAY": .93, "DOUBTFUL": .75,
          "OUT": .6, "SUSPENSION": .6, "INJURY_RESERVE": .5}
WEIGHTS = {"QB": .13, "RB": .22, "WR": .22, "TE": .10, "FLEX": .09, "Bench": .07,
           "Depth": .06, "Upside": .06, "Health": .05}
FLEX_POS = ("RB", "WR", "TE")


def project(p, week):
    """Blend recent form, season-to-date and the preseason prior into expected/floor/ceiling ppg."""
    s, pos = p.get("stats", {}), p["pos"]
    games = sorted((int(w), v) for w, v in s.get("weekly", {}).items() if int(w) <= week and v != 0)
    vals = [v for _, v in games]
    n = len(vals)
    prior_parts = [(s.get("proj_ppg_2026"), .6), (s.get("ppg_2025"), .4)]
    prior_parts = [(v, w) for v, w in prior_parts if v]
    prior = sum(v * w for v, w in prior_parts) / sum(w for _, w in prior_parts) if prior_parts else DEFAULT_PPG[pos]
    if n:
        wts = [RECENCY ** (n - 1 - i) for i in range(n)]
        recent = sum(v * w for v, w in zip(vals, wts)) / sum(wts)
        actual = .6 * recent + .4 * (sum(vals) / n)
        mean = (n * actual + K_PRIOR * prior) / (n + K_PRIOR)
    else:
        mean = prior
    w_obs = n / (n + K_PRIOR)
    sd_prior = CV[pos] * mean
    sd = math.sqrt(w_obs * stats.pstdev(vals) ** 2 + (1 - w_obs) * sd_prior ** 2) if n >= 3 else sd_prior
    f = HEALTH.get(p.get("injury", "ACTIVE"), .9)
    return {"sd": sd * f, "ppg": mean * f, "floor": max(0, mean - 1.28 * sd) * f, "ceil": (mean + 1.28 * sd) * f,
            "conf": round(w_obs, 2), "health": f, "raw_ppg": mean}


def zscore_scores(values):
    """0-100 score per team: logistic of the league z-score, so 50 = league average."""
    mu, sd = stats.mean(values.values()), stats.pstdev(values.values()) or 1
    return {k: 100 / (1 + math.exp(-1.2 * (v - mu) / sd)) for k, v in values.items()}


def pick_lineup(players, slots):
    """Greedy-optimal for dedicated slots + one FLEX pool: take the best at each position, then the best leftover flex-eligible."""
    by = {pos: sorted([p for p in players if p["pos"] == pos], key=lambda p: -p["ppg"]) for pos in C.POSITIONS.values()}
    take = {"QB": slots.get("QB", 0), "RB": slots.get("RB", 0), "WR": slots.get("WR", 0),
            "TE": slots.get("TE", 0), "K": slots.get("K", 0), "D/ST": slots.get("D/ST", 0)}
    lineup = {pos: by[pos][:n] for pos, n in take.items()}
    left = sorted([p for pos in FLEX_POS for p in by[pos][take[pos]:]], key=lambda p: -p["ppg"])
    lineup["FLEX"] = left[:slots.get("FLEX", 0)]
    starters = {p["id"] for v in lineup.values() for p in v}
    return lineup, [p for p in players if p["id"] not in starters]


def ppg_at(lineup, pos, i):
    return lineup[pos][i]["ppg"] if i < len(lineup[pos]) else 0.0


def analyze(name):
    snap = json.loads((DATA / name / "snapshot.json").read_text())
    S, week = snap["settings"], snap["settings"]["current_week"]
    slots, nteams = S["lineup_slots"], S["num_teams"]
    teams = {t["id"]: t for t in snap["teams"]}
    me = snap["my_team_id"]

    for p in [p for t in snap["teams"] for p in t["roster"]] + snap["free_agents"]:
        p.update(project(p, week))
    healthy_fa = [p for p in snap["free_agents"] if p["injury"] in ("ACTIVE", "NORMAL", "QUESTIONABLE", "DAY_TO_DAY")]
    repl = {}
    for pos in ("QB", "RB", "WR", "TE"):
        top = sorted((p["ppg"] for p in healthy_fa if p["pos"] == pos), reverse=True)
        repl[pos] = top[2] if len(top) > 2 else DEFAULT_PPG[pos]

    # ---- per-team lineup + category raw values ----
    raw, lineups, benches = {}, {}, {}
    for tid, t in teams.items():
        active = [p for p in t["roster"] if p["slot"] != "IR"]
        lu, bench = pick_lineup(active, slots)
        lineups[tid], benches[tid] = lu, bench
        starters = [p for v in lu.values() for p in v]
        core_bench = sorted([p for p in bench if p["pos"] in ("QB",) + FLEX_POS], key=lambda p: -p["ppg"])
        tot = sum(p["raw_ppg"] for p in starters) or 1
        raw[tid] = {
            "QB": ppg_at(lu, "QB", 0), "RB": ppg_at(lu, "RB", 0) + ppg_at(lu, "RB", 1),
            "WR": ppg_at(lu, "WR", 0) + ppg_at(lu, "WR", 1), "TE": ppg_at(lu, "TE", 0),
            "FLEX": ppg_at(lu, "FLEX", 0),
            "Bench": sum(p["ppg"] for p in core_bench[:4]),
            "Depth": sum(max(0, p["ppg"] - repl[p["pos"]]) for p in core_bench),
            "Upside": sum(p["ceil"] for p in starters),
            "Health": 1 - sum(p["raw_ppg"] * (1 - p["health"]) for p in starters) / tot,
            "proj_total": sum(p["ppg"] for p in starters),
            # Player outcomes are treated as independent, so team spread adds in quadrature (P10/P90).
            "floor": sum(p["ppg"] for p in starters) - 1.28 * math.sqrt(sum(p["sd"] ** 2 for p in starters)),
            "ceil": sum(p["ppg"] for p in starters) + 1.28 * math.sqrt(sum(p["sd"] ** 2 for p in starters)),
        }
    cats = {c: zscore_scores({tid: r[c] for tid, r in raw.items()}) for c in WEIGHTS if c != "Health"}
    # Health differences between teams are tiny, so z-scoring would blow up noise: score it absolutely.
    cats["Health"] = {tid: 100 * r["Health"] for tid, r in raw.items()}
    roster_score = {tid: sum(WEIGHTS[c] * cats[c][tid] for c in WEIGHTS) for tid in teams}

    # ---- results, expected wins, standings ----
    done = [g for g in snap["schedule"] if g["week"] < week and "away" in g and not g["playoff"]]
    weeks = sorted({g["week"] for g in done})
    ew = {tid: 0.0 for tid in teams}
    for w in weeks:
        sc = {}
        for g in done:
            if g["week"] == w:
                sc[g["home"]], sc[g["away"]] = g["home_pts"], g["away_pts"]
        for tid, v in sc.items():
            others = [x for k, x in sc.items() if k != tid]
            ew[tid] += (sum(v > x for x in others) + .5 * sum(v == x for x in others)) / len(others)
    order = sorted(teams.values(), key=lambda t: (-t["wins"], -t["points_for"]))
    rank = {t["id"]: i + 1 for i, t in enumerate(order)}
    cut_n = S["schedule"].get("playoffTeamCount", 6)
    cutoff = order[cut_n - 1]
    reg_weeks = S["schedule"]["matchupPeriodCount"]
    remaining = {tid: [] for tid in teams}
    for g in snap["schedule"]:
        if week <= g["week"] <= reg_weeks and "away" in g and not g["playoff"]:
            remaining[g["home"]].append(g["away"])
            remaining[g["away"]].append(g["home"])
    sos = {tid: stats.mean(roster_score[o] for o in opps) if opps else 50 for tid, opps in remaining.items()}

    gp = max(len(weeks), 1)
    power_parts = {
        "roster": roster_score,
        "expected_win_rate": zscore_scores({k: v / gp for k, v in ew.items()}),
        "win_pct": zscore_scores({k: (t["wins"] + .5 * t["ties"]) / max(t["wins"] + t["losses"] + t["ties"], 1) for k, t in teams.items()}),
        "schedule_ease": zscore_scores({k: -v for k, v in sos.items()}),
    }
    pw = {"roster": .55, "expected_win_rate": .20, "win_pct": .15, "schedule_ease": .10}
    power = {tid: sum(pw[k] * power_parts[k][tid] for k in pw) for tid in teams}
    power_rank = {tid: i + 1 for i, tid in enumerate(sorted(power, key=power.get, reverse=True))}

    def label(tid):
        t, diff = teams[tid], teams[tid]["wins"] - ew[tid]
        luck = "LUCKY" if diff > .75 else "UNLUCKY" if diff < -.75 else "as expected"
        good_rec, good_roster = rank[tid] <= cut_n, roster_score[tid] >= 50
        legit = roster_score[tid] >= 55 and power_rank[tid] <= cut_n
        kind = {(1, 1): "strong record + strong roster", (1, 0): "strong record + weak roster",
                (0, 1): "weak record + strong roster", (0, 0): "weak record + weak roster"}[(good_rec, good_roster)]
        tag = "LEGIT CONTENDER" if legit else "FAKE CONTENDER" if good_rec and not good_roster else ""
        return {"luck": luck, "profile": kind, "tag": tag}

    # ---- positional ranks, needs, surplus ----
    slot_vals = {  # slot label -> {team: ppg}
        "QB": {t: ppg_at(lineups[t], "QB", 0) for t in teams},
        "RB1": {t: ppg_at(lineups[t], "RB", 0) for t in teams}, "RB2": {t: ppg_at(lineups[t], "RB", 1) for t in teams},
        "WR1": {t: ppg_at(lineups[t], "WR", 0) for t in teams}, "WR2": {t: ppg_at(lineups[t], "WR", 1) for t in teams},
        "TE": {t: ppg_at(lineups[t], "TE", 0) for t in teams}, "FLEX": {t: ppg_at(lineups[t], "FLEX", 0) for t in teams},
    }
    slot_rank = {s: {t: 1 + sum(v > d[t] for v in d.values()) for t in teams} for s, d in slot_vals.items()}
    pos_rank = {pos: {t: 1 + sum(raw[o][pos] > raw[t][pos] for o in teams) for t in teams} for pos in ("QB", "RB", "WR", "TE", "FLEX", "Bench")}
    thresh = {pos: sorted(slot_vals[s].values())[nteams // 4] for pos, s in (("QB", "QB"), ("RB", "RB2"), ("WR", "WR2"), ("TE", "TE"))}
    surplus = {}
    for tid in teams:
        surplus[tid] = {pos: [p for p in benches[tid] if p["pos"] == pos and p["ppg"] >= thresh[pos]] for pos in thresh}
    best_fa = {pos: sorted([p for p in healthy_fa if p["pos"] == pos], key=lambda p: -p["ppg"])[:3] for pos in ("QB", "RB", "WR", "TE", "K", "D/ST")}

    def need_tier(r):
        return ("No meaningful need" if r <= 3 else "Moderate upgrade opportunity" if r <= 6
                else "Major upgrade opportunity" if r <= 9 else "CRITICAL need")

    my_needs = []
    for s, d in slot_vals.items():
        pos = s.rstrip("12") if s != "FLEX" else "FLEX"
        pool = best_fa.get(pos) if pos != "FLEX" else sorted([p for pp in FLEX_POS for p in best_fa[pp]], key=lambda p: -p["ppg"])
        fa = pool[0] if pool else None
        p75 = sorted(d.values(), reverse=True)[max(nteams // 4 - 1, 0)]
        my_needs.append({"slot": s, "mine": round(d[me], 1), "rank": slot_rank[s][me], "tier": need_tier(slot_rank[s][me]),
                         "gain_to_top_quartile": round(max(0, p75 - d[me]), 1),
                         "best_free_agent": f'{fa["name"]} ({fa["ppg"]:.1f})' if fa else None,
                         "waiver_gain": round(max(0, fa["ppg"] - d[me]), 1) if fa else 0})
    my_needs.sort(key=lambda n: -n["gain_to_top_quartile"])

    out = {"league": S["name"], "refreshed_at": snap["refreshed_at"], "week": week, "my_team_id": me, "teams": {}}
    for tid, t in teams.items():
        strengths = [f"{s} (#{slot_rank[s][tid]})" for s in slot_vals if slot_rank[s][tid] <= 3]
        weaknesses = [f"{s} (#{slot_rank[s][tid]})" for s in slot_vals if slot_rank[s][tid] >= nteams - 3]
        out["teams"][tid] = {
            "name": t["name"], "record": f'{t["wins"]}-{t["losses"]}-{t["ties"]}', "points_for": t["points_for"],
            "standing": rank[tid], "expected_wins": round(ew[tid], 2), **label(tid),
            "roster_score": round(roster_score[tid], 1), "power_rank": power_rank[tid], "power": round(power[tid], 1),
            "categories": {c: round(cats[c][tid], 1) for c in WEIGHTS},
            "weekly": {k: round(raw[tid][k], 1) for k in ("floor", "proj_total", "ceil")},
            "remaining_sos": round(sos[tid], 1), "remaining_opponents": remaining[tid],
            "strengths": strengths, "weaknesses": weaknesses,
            "surplus": {pos: [f'{p["name"]} ({p["ppg"]:.1f})' for p in v] for pos, v in surplus[tid].items() if v},
            "demand": [pos for pos in ("QB", "RB", "WR", "TE") if pos_rank[pos][tid] > nteams - 4],
            "lineup": {k: [f'{p["name"]} ({p["ppg"]:.1f})' for p in v] for k, v in lineups[tid].items()},
            "out_or_ir": [f'{p["name"]} ({p["injury"]})' for p in t["roster"] if p["injury"] in ("OUT", "INJURY_RESERVE", "DOUBTFUL")],
        }
    market = {pos: {"excess": [teams[t]["name"] for t in teams if surplus[t][pos]],
                    "needs": [teams[t]["name"] for t in teams if pos_rank[pos][t] > nteams - 4]} for pos in thresh}
    out.update(my_needs=my_needs, market=market, cutoff={"seed": cut_n, "team": cutoff["name"],
               "record": f'{cutoff["wins"]}-{cutoff["losses"]}', "my_games_back": ((cutoff["wins"] - teams[me]["wins"]) + (teams[me]["losses"] - cutoff["losses"])) / 2},
               best_free_agents={k: [f'{p["name"]} ({p["ppg"]:.1f})' for p in v] for k, v in best_fa.items()},
               assumptions={"K_PRIOR": K_PRIOR, "RECENCY": RECENCY, "HEALTH": HEALTH, "WEIGHTS": WEIGHTS, "power_weights": pw})
    (DATA / name / "analysis.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def report(a):
    me = str(a["my_team_id"])
    teams = {str(k): v for k, v in a["teams"].items()}
    L = [f'# {a["league"]} — week {a["week"]}  (data refreshed {a["refreshed_at"]})', "",
         "## Power rankings", "", "| # | Team | Rec | Standing | xWins | Roster | Power | Verdict |", "|--|--|--|--|--|--|--|--|"]
    for t in sorted(teams.items(), key=lambda kv: kv[1]["power_rank"]):
        v = t[1]
        mark = " **(me)**" if t[0] == me else ""
        L.append(f'| {v["power_rank"]} | {v["name"]}{mark} | {v["record"]} | {v["standing"]} | {v["expected_wins"]} | '
                 f'{v["roster_score"]} | {v["power"]} | {v["luck"]}{", " + v["tag"] if v["tag"] else ""} — {v["profile"]} |')
    m = teams[me]
    L += ["", f'## My team: {m["name"]}', f'Standing {m["standing"]}, cutoff is seed {a["cutoff"]["seed"]} ({a["cutoff"]["team"]}, {a["cutoff"]["record"]}); '
          f'I am {a["cutoff"]["my_games_back"]} games back. Projected weekly points: floor {m["weekly"]["floor"]} / median {m["weekly"]["proj_total"]} / ceiling {m["weekly"]["ceil"]}.',
          "", "Category scores (0-100, 50 = league average): " + ", ".join(f"{k} {v}" for k, v in m["categories"].items()),
          "", "### Needs (ranked by upgrade to league top-quartile starter)", "", "| Slot | Mine | Rank | Tier | Gain to top-quartile | Best FA | Waiver gain |", "|--|--|--|--|--|--|--|"]
    for n in a["my_needs"]:
        L.append(f'| {n["slot"]} | {n["mine"]} | {n["rank"]} | {n["tier"]} | +{n["gain_to_top_quartile"]} | {n["best_free_agent"]} | +{n["waiver_gain"]} |')
    L += ["", "## Opponent profiles", ""]
    for k, v in sorted(teams.items(), key=lambda kv: kv[1]["power_rank"]):
        if k == me:
            continue
        L.append(f'**{v["name"]}** — strengths: {", ".join(v["strengths"]) or "none"}; weaknesses: {", ".join(v["weaknesses"]) or "none"}; '
                 f'trade surplus: {"; ".join(p + ": " + ", ".join(x) for p, x in v["surplus"].items()) or "none"}; demand: {", ".join(v["demand"]) or "none"}; '
                 f'injured: {", ".join(v["out_or_ir"]) or "none"}')
    L += ["", "## Market map", ""]
    for pos, v in a["market"].items():
        L.append(f'- **{pos}** excess: {", ".join(v["excess"]) or "-"} | needs: {", ".join(v["needs"]) or "-"}')
    L += ["", "## Best free agents / waivers (by blended ppg)", ""]
    for pos, v in a["best_free_agents"].items():
        L.append(f'- {pos}: {", ".join(v)}')
    return "\n".join(L)


if __name__ == "__main__":
    for lg in sys.argv[1:] or C.LEAGUES:
        a = analyze(lg)
        text = report(a)
        (DATA / lg / "report.md").write_text(text)
        print(text, "\n")
