"""LEAGUE GM and ANALYZE MATCHUP modes.

    python -m fantasy.gm cuzff legoat            # RUN LEAGUE GM  -> data/<league>/gm.md
    python -m fantasy.gm cuzff --matchup         # ANALYZE MATCHUP (this week's opponent)
"""
import sys
import time

import numpy as np

from . import analyze as A
from . import config as C
from . import model as M
from .simulate import Sim, waiver_scan
from .trades import Trader, names


def partner_scores(tr, an):
    """0-100: how well a manager's needs/surplus line up with mine, blended with the best deal found with them."""
    me = str(tr.me)
    mine = an["teams"][me] if me in an["teams"] else an["teams"][tr.me]
    my_demand, my_surplus = set(mine["demand"]), set(mine["surplus"])
    best = max(tr.partner_best.values() or [1e-9]) or 1e-9
    out = {}
    for tid, t in tr.tid.items():
        if tid == tr.me:
            continue
        a = an["teams"].get(tid) or an["teams"][str(tid)]
        comp = 25 * len(my_demand & set(a["surplus"])) + 25 * len(set(a["demand"]) & my_surplus)
        out[tid] = round(.5 * min(100, comp) + .5 * 100 * tr.partner_best.get(tid, 0) / best, 1)
    return out


def breakout_watch(sim, n=3):
    """Free agents whose role is growing faster than their production: snap share trend + target/carry share."""
    rows = []
    for p in sim.snap["free_agents"]:
        u = p.get("usage") or {}
        if "snap_recent" not in u or p["pos"] not in ("RB", "WR", "TE"):
            continue
        score = 100 * (u["snap_recent"] - u["snap_season"]) + 100 * (u.get("target_share", 0) + .5 * u.get("carry_share", 0))
        rows.append((score, p))
    return sorted(rows, key=lambda x: -x[0])[:n]


def run_gm(lg):
    sim = Sim(lg, 10000)
    sim.calibrate()
    base = sim.run()
    an = A.analyze(lg)
    tr = Trader(sim)
    _, rows = tr.scan(base)
    wv = waiver_scan(sim, base)
    me = sim.snap["my_team_id"]
    T = lambda tid: an["teams"].get(tid) or an["teams"][str(tid)]
    mt, nm = T(me), {t["id"]: t["name"] for t in sim.snap["teams"]}
    ps = partner_scores(tr, an)
    o = base[me]
    L = [f'# LEAGUE GM — {an["league"]} (week {an["week"]})',
         f'_Data freshness: ESPN league {an["refreshed_at"]} · nflverse {an["nfl_refreshed_at"]} · generated {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}._', "",
         "## MY TEAM", f'**{mt["name"]}** · Record {mt["record"]} · Standing {mt["standing"]} · Points For {mt["points_for"]} · Expected wins {mt["expected_wins"]} · '
         f'Roster score {mt["roster_score"]} · Playoffs {o["playoffs"]*100:.0f}% · Bye {o["bye"]*100:.0f}% · Title game {o["final"]*100:.0f}% · **Title {o["title"]*100:.1f}%**', "",
         "## POWER RANKINGS"]
    for tid, t in sorted(an["teams"].items(), key=lambda kv: kv[1]["power_rank"]):
        L.append(f'{t["power_rank"]}. {t["name"]} — {t["record"]}, roster {t["roster_score"]}, title {base[int(tid)]["title"]*100:.1f}% ({t["luck"]}{", " + t["tag"] if t["tag"] else ""})')
    threats = sorted([t for t in base if t != me], key=lambda t: -base[t]["title"])[:3]
    L += ["", "## BIGGEST CHAMPIONSHIP THREATS"]
    for i, t in enumerate(threats, 1):
        a = T(t)
        L.append(f'{i}. **{nm[t]}** ({base[t]["title"]*100:.1f}%): strengths {", ".join(a["strengths"]) or "—"}; weaknesses {", ".join(a["weaknesses"]) or "—"}; injuries {", ".join(a["out_or_ir"]) or "none"}')
    L += ["", "## MY BIGGEST NEEDS"]
    for i, n in enumerate(an["my_needs"][:3], 1):
        L.append(f'{i}. **{n["slot"]}** — {n["tier"]}: mine {n["mine"]} ppg (#{n["rank"]}); +{n["gain_to_top_quartile"]} ppg to reach top quartile')
    L += ["", "## BEST TRADE PARTNERS"]
    for i, (t, sc) in enumerate(sorted(ps.items(), key=lambda kv: -kv[1])[:3], 1):
        a = T(t)
        L.append(f'{i}. **{nm[t]}** (partner score {sc}) — surplus {", ".join(a["surplus"]) or "—"}; needs {", ".join(a["demand"]) or "—"}; {trader_style(tr, t)}')
    L += ["", "## BEST PLAYERS TO TARGET"]
    for i, r in enumerate(rows[:5], 1):
        p, f = r["target"], r["offers"]["fair"]
        L.append(f'{i}. **{p["name"]}** ({p["pos"]}) from {nm[r["owner"]]} — {r["class"]}, fit {r["fit"]}, title {o["title"]*100:.1f}% → {f["title_after"]*100:.1f}%')
    L += ["", "## BUY LOW"]
    seen = 0
    for gap, g, tid, p in tr.buy_low:
        if seen == 3:
            break
        if gap >= 1.0:
            L.append(f'{seen+1}. **{p["name"]}** ({nm[tid]}) — projects {p["ppg"]:.1f} ppg vs market-implied {tr.market[p["id"]] + tr.repl[p["pos"]]:.1f}; lifts my lineup {g:+.1f}/wk')
            seen += 1
    L += ["", "## SELL HIGH (market likes them more than my model does)"]
    mine = sorted([(tr.market[p["id"]] - tr.true[p["id"]], p) for p in sim.snap["teams"][sim.tidx[me]]["roster"] if p["pos"] in M.POS], key=lambda x: -x[0])[:3]
    for i, (gap, p) in enumerate(mine, 1):
        L.append(f'{i}. **{p["name"]}** ({p["pos"]}) — model {p["ppg"]:.1f} ppg; market gap {gap:+.1f} ppg over replacement')
    L += ["", "## WAIVER PRIORITIES (waiver rank: " + str(sim.snap["teams"][sim.tidx[me]]["waiver_rank"]) + ")"]
    for i, w in enumerate(wv[:3], 1):
        pos = w["add"].split("(")[1].split(",")[0]
        rivals = an["market"].get(pos, {}).get("needs", [])[:3]
        L.append(f'{i}. Add {w["add"]}, drop {w["drop"]} — title {w["d_title"]*100:+.2f} pts, playoffs {w["d_playoffs"]*100:+.1f} pts. Others needing {pos}: {", ".join(rivals) or "none"}.')
    L += ["", "## BREAKOUT WATCH (free agents with growing roles)"]
    for i, (sc, p) in enumerate(breakout_watch(sim), 1):
        u = p["usage"]
        L.append(f'{i}. **{p["name"]}** ({p["pos"]}, {p["nfl_team"]}) — snap share {u["snap_season"]*100:.0f}% → {u["snap_recent"]*100:.0f}% recent; target share {u.get("target_share", 0)*100:.0f}%')
    L += ["", "## THREE MOVES I SHOULD MAKE"]
    moves, used_pos, used_owner = [], set(), set()
    keep = max(sim.snap["teams"][sim.tidx[me]]["roster"], key=lambda p: tr.true[p["id"]])
    for r in rows:
        if len(moves) == 2:
            break
        if r["target"]["pos"] in used_pos or r["owner"] in used_owner:
            continue
        o_, f = r["offers"], r["offers"]["fair"]
        extra = f'If rejected, move to {names(tr, o_["aggressive"]["give"])}.' if o_.get("aggressive") and o_["aggressive"]["d_title"] > 0 else "Don't chase past the fair offer."
        moves.append(f'Target **{r["target"]["name"]}** from {nm[r["owner"]]}. Open with {names(tr, o_["opening"]["give"] if o_.get("opening") and o_["opening"]["d_title"] > 0 else f["give"])}. '
                     f'Expected deal: {names(tr, f["give"])} ({f["accept"]*100:.0f}% to accept, title {o["title"]*100:.1f}% → {f["title_after"]*100:.1f}%). {extra} Do not include {keep["name"]}.')
        used_pos.add(r["target"]["pos"]); used_owner.add(r["owner"])
    if wv:
        w = wv[0]
        moves.append(f'Waivers: add {w["add"]} and drop {w["drop"]} (title {w["d_title"]*100:+.2f} pts).')
    for i, m in enumerate(moves, 1):
        L.append(f"{i}. {m}")
    text = "\n".join(L)
    (C.DATA_DIR / lg / "gm.md").write_text(text)
    return text


def trader_style(tr, tid):
    t = tr.tid[tid]
    tr_n, mv = t.get("trades") or 0, t.get("moves") or 0
    return ("active trader" if tr_n >= 3 else "occasional trader" if tr_n >= 1 else "has not traded") + (", waiver-heavy" if mv >= 10 else "")


def run_matchup(lg):
    sim = Sim(lg, 10000)
    sim.calibrate()
    me, w = sim.snap["my_team_id"], sim.week
    opp = next((g["away"] if g["home"] == me else g["home"] for g in sim.snap["schedule"]
                if g["week"] == w and "away" in g and me in (g["home"], g["away"])), None)
    nm = {t["id"]: t["name"] for t in sim.snap["teams"]}
    rost = {t["id"]: t["roster"] for t in sim.snap["teams"]}
    game = next(g for g in sim.snap["schedule"] if g["week"] == w and "away" in g and me in (g["home"], g["away"]))
    espn_wp = game.get("home_win_prob")
    if espn_wp is not None and game["home"] != me:
        espn_wp = 1 - espn_wp
    a, b = sim.team_week(me, rost[me], w), sim.team_week(opp, rost[opp], w)
    q = lambda x: [float(np.percentile(x, p)) for p in (10, 50, 90)]
    qa, qb = q(a), q(b)
    L = [f'## ANALYZE MATCHUP — {nm[me]} vs {nm[opp]} (week {w}; ESPN {sim.snap["refreshed_at"]}, nflverse {sim.snap["nfl_refreshed_at"]})',
         f'- Live points now: {sim.live[me]:.1f} vs {sim.live[opp]:.1f}',
         f'- **Projected final** (floor/median/ceiling): me {qa[0]:.0f} / {qa[1]:.0f} / {qa[2]:.0f} · opponent {qb[0]:.0f} / {qb[1]:.0f} / {qb[2]:.0f}',
         f'- **WIN PROBABILITY: {np.mean(a > b)*100:.0f}%**' + (f' (ESPN shows {espn_wp*100:.0f}%)' if espn_wp is not None else "")]
    tonight = [p for p in rost[me] if p["slot"] not in (None, "BE", "IR") and (g := sim.nfl.game(w, p["nfl_team"])) and not g["done"]]
    L.append("- Players still to play (mine): " + (", ".join(f'{p["name"]} ({p["nfl_team"]}, {p["ppg"]:.1f})' for p in tonight) or "none"))
    tonight_o = [p for p in rost[opp] if p["slot"] not in (None, "BE", "IR") and (g := sim.nfl.game(w, p["nfl_team"])) and not g["done"]]
    L.append("- Players still to play (opponent): " + (", ".join(f'{p["name"]} ({p["nfl_team"]}, {p["ppg"]:.1f})' for p in tonight_o) or "none"))
    risk = [p for p in rost[me] if p["slot"] not in (None, "BE", "IR") and p["injury"] not in ("ACTIVE", "NORMAL")]
    L.append("- Injury risks in my lineup: " + (", ".join(f'{p["name"]} ({p["injury"]})' for p in risk) or "none"))
    text = "\n".join(L)
    (C.DATA_DIR / lg / "matchup.md").write_text(text)
    return text


if __name__ == "__main__":
    args = sys.argv[1:]
    matchup = "--matchup" in args
    for lg in [a for a in args if not a.startswith("--")] or C.LEAGUES:
        print(run_matchup(lg) if matchup else run_gm(lg), "\n")
