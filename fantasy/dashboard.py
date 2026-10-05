"""Build data/dashboard.json (everything the dashboard page shows) for every league.

    python -m fantasy.dashboard
"""
import json
import time

import numpy as np

from . import analyze as A
from . import config as C
from . import model as M
from .gm import breakout_watch, partner_scores
from .simulate import Sim, waiver_scan
from .trades import Trader, names


def build(lg):
    sim = Sim(lg, 10000)
    sim.calibrate()
    base = sim.run()
    an = A.analyze(lg)
    tr = Trader(sim)
    _, rows = tr.scan(base)
    wv = waiver_scan(sim, base)
    me = sim.snap["my_team_id"]
    nm = {t["id"]: t["name"] for t in sim.snap["teams"]}
    ps = partner_scores(tr, an)
    T = lambda tid: an["teams"].get(tid) or an["teams"][str(tid)]

    teams = []
    for tid in sim.team_ids:
        a, o = T(tid), base[tid]
        teams.append({"id": tid, "name": nm[tid], "me": tid == me, "record": a["record"], "standing": a["standing"],
                      "pf": a["points_for"], "xwins": a["expected_wins"], "roster": a["roster_score"], "power_rank": a["power_rank"],
                      "luck": a["luck"], "tag": a["tag"], "playoffs": o["playoffs"], "bye": o["bye"], "final": o["final"],
                      "title": o["title"], "cats": a["categories"], "strengths": a["strengths"], "weaknesses": a["weaknesses"],
                      "surplus": list(a["surplus"]), "demand": a["demand"], "injured": a["out_or_ir"],
                      "partner": ps.get(tid)})

    game = next(g for g in sim.snap["schedule"] if g["week"] == sim.week and "away" in g and me in (g["home"], g["away"]))
    opp = game["away"] if game["home"] == me else game["home"]
    rost = {t["id"]: t["roster"] for t in sim.snap["teams"]}
    x, y = sim.team_week(me, rost[me], sim.week), sim.team_week(opp, rost[opp], sim.week)
    wp = game.get("home_win_prob")
    if wp is not None and game["home"] != me:
        wp = 1 - wp
    q = lambda v: [round(float(np.percentile(v, p)), 1) for p in (10, 50, 90)]
    pending = [f'{p["name"]} ({p["nfl_team"]})' for p in rost[me] if p["slot"] not in (None, "BE", "IR")
               and (g := sim.nfl.game(sim.week, p["nfl_team"])) and not g["done"]]

    def offer(e):
        return None if not e else {"give": names(tr, e["give"]), "accept": e["accept"], "gain_me": e["gain_me"], "gain_them": e["gain_them"],
                                   "title_after": e["title_after"], "d_title": e["d_title"]}
    trades = [{"target": r["target"]["name"], "pos": r["target"]["pos"], "nfl": r["target"]["nfl_team"], "owner": nm[r["owner"]],
               "klass": r["class"], "fit": r["fit"], "ppg": round(r["target"]["ppg"], 1), "floor": round(r["target"]["floor"], 1),
               "ceil": round(r["target"]["ceil"], 1), "gap": round(r["gap"], 1), "roi": round(r["roi"], 2),
               "offers": {k: offer(v) for k, v in r["offers"].items()}} for r in rows]
    needs = an["my_needs"]
    return {"league": an["league"], "week": an["week"], "espn_refreshed": an["refreshed_at"], "nfl_refreshed": an["nfl_refreshed_at"],
            "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sims": sim.S, "my_id": me, "teams": teams, "needs": needs,
            "market": an["market"], "cutoff": an["cutoff"], "trades": trades,
            "waivers": [{"add": w["add"], "drop": w["drop"], "d_playoffs": w["d_playoffs"], "d_title": w["d_title"]} for w in wv[:5]],
            "breakouts": [{"name": p["name"], "pos": p["pos"], "team": p["nfl_team"], "snap_season": p["usage"]["snap_season"],
                           "snap_recent": p["usage"]["snap_recent"], "target_share": p["usage"].get("target_share", 0)} for _, p in breakout_watch(sim, 4)],
            "matchup": {"opp": nm[opp], "live_me": sim.live[me], "live_opp": sim.live[opp], "me": q(x), "opp_q": q(y),
                        "win": float(np.mean(x > y)), "espn_win": wp, "pending": pending},
            "calibration": getattr(sim, "calibration", None)}


if __name__ == "__main__":
    out = {lg: build(lg) for lg in C.LEAGUES}
    (C.DATA_DIR / "dashboard.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", C.DATA_DIR / "dashboard.json")
