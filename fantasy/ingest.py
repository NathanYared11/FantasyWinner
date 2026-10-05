"""Stage 1: pull a full ESPN league snapshot (settings, every team, rosters, schedule,
transactions, free agents) and write it to data/<league>/snapshot.json.

    python -m fantasy.ingest cuzff legoat
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from . import config as C

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{lid}"
DATA = Path(__file__).resolve().parent.parent / "data"


def fetch(name, views, fantasy_filter=None):
    s2, swid = C.credentials()
    url = API.format(season=C.SEASON, lid=C.league_id(name)) + "?" + "&".join("view=" + v for v in views)
    # curl (not urllib) so the sandbox proxy and CA bundle are honored; credentials stay off argv
    # by passing headers on stdin.
    headers = f"Cookie: espn_s2={s2}; SWID={swid}\n"
    if fantasy_filter:
        headers += "X-Fantasy-Filter: " + json.dumps(fantasy_filter) + "\n"
    out = subprocess.run(["curl", "-sS", "-m", "90", "--fail-with-body", "-H", "@-", url],
                         input=headers, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"ESPN fetch failed for {name}: {out.stderr.strip() or out.stdout[:200]}")
    return json.loads(out.stdout)


def player_row(entry):
    pool = entry.get("playerPoolEntry", entry)
    p = pool["player"]
    return {
        "id": p["id"],
        "name": p["fullName"],
        "pos": C.POSITIONS.get(p["defaultPositionId"], str(p["defaultPositionId"])),
        "nfl_team": C.PRO_TEAMS.get(p.get("proTeamId"), str(p.get("proTeamId"))),
        "injury": p.get("injuryStatus", "ACTIVE"),
        "pct_owned": round(p.get("ownership", {}).get("percentOwned", 0), 1),
        "season_pts": round(pool.get("appliedStatTotal", 0), 2),
        "slot": C.LINEUP_SLOTS.get(entry.get("lineupSlotId"), None),
        "acquired": entry.get("acquisitionType"),
    }


def player_stats(name, ids):
    """Weekly actuals, ESPN projections and season averages per player. Points are already scored
    by the league's own rules, so scoring items never need decoding."""
    out = {}
    periods = ["002025", "102025", "002026", "102026"] + [f"11{C.SEASON}{w}" for w in range(1, 19)]
    for i in range(0, len(ids), 120):
        flt = {"players": {"filterIds": {"value": ids[i:i + 120]},
                           "filterStatsForTopScoringPeriodIds": {"value": 5, "additionalValue": periods}}}
        for p in fetch(name, ["kona_playercard"], flt)["players"]:
            st = {"weekly": {}, "proj_week": {}, "ppg_2026": None, "games_2026": 0,
                  "proj_ppg_2026": None, "ppg_2025": None}
            for x in p["player"].get("stats", []):
                sid, src, split, wk = x["id"], x["statSourceId"], x["statSplitTypeId"], x.get("scoringPeriodId")
                if split == 1 and x.get("seasonId") != C.SEASON:
                    continue
                if src == 0 and split == 1:
                    st["weekly"][wk] = round(x.get("appliedTotal", 0), 2)
                elif src == 1 and split == 1:
                    st["proj_week"][wk] = round(x.get("appliedTotal", 0), 2)
                elif sid == "002026" and x.get("appliedAverage"):
                    st["ppg_2026"] = round(x["appliedAverage"], 2)
                    st["games_2026"] = round(x["appliedTotal"] / x["appliedAverage"])
                elif sid == "102026":
                    st["proj_ppg_2026"] = x.get("appliedAverage")
                elif sid == "002025":
                    st["ppg_2025"] = x.get("appliedAverage")
            out[p["id"]] = st
    return out


def build_settings(d):
    s = d["settings"]
    sched = {k: v for k, v in s["scheduleSettings"].items() if k != "matchupPeriods"}
    counts = {C.LINEUP_SLOTS.get(int(k), k): v for k, v in s["rosterSettings"]["lineupSlotCounts"].items() if v}
    return {
        "league_id": d["id"], "name": s["name"], "season": d["seasonId"], "num_teams": s["size"],
        "current_week": d["scoringPeriodId"],
        "lineup_slots": counts,
        "position_limits": s["rosterSettings"]["positionLimits"],
        "bench_unlimited": s["rosterSettings"].get("isBenchUnlimited"),
        "schedule": sched,
        "acquisition": s["acquisitionSettings"],
        "trade": s["tradeSettings"],
        "scoring_rank_type": s["scoringSettings"].get("playerRankType"),
        "scoring_items": s["scoringSettings"]["scoringItems"],  # raw: statId -> points; decoded in Stage 2
    }


def ingest(name):
    base = fetch(name, ["mSettings", "mTeam", "mStandings"])
    roster = fetch(name, ["mRoster"])
    sched = fetch(name, ["mMatchup", "mMatchupScore"])
    tx = fetch(name, ["mTransactions2"])
    fa = fetch(name, ["kona_player_info"], {"players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 400,
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})

    members = {m["id"]: m.get("displayName", "") for m in base.get("members", [])}
    rosters = {t["id"]: t["roster"]["entries"] for t in roster["teams"]}
    teams = []
    for t in base["teams"]:
        entries = [player_row(e) for e in rosters.get(t["id"], [])]
        rec = t["record"]["overall"]
        teams.append({
            "id": t["id"], "name": t.get("name"), "abbrev": t.get("abbrev"),
            "managers": [members.get(o, o) for o in t.get("owners", [])],
            "wins": rec["wins"], "losses": rec["losses"], "ties": rec["ties"],
            "points_for": round(rec["pointsFor"], 2), "points_against": round(rec["pointsAgainst"], 2),
            "standing": t.get("rankCalculatedFinal") or t.get("playoffSeed"),
            "waiver_rank": t.get("waiverRank"),
            "faab_remaining": t.get("transactionCounter", {}).get("acquisitionBudgetSpent") is not None and
                              base["settings"]["acquisitionSettings"]["acquisitionBudget"]
                              - t["transactionCounter"]["acquisitionBudgetSpent"],
            "moves": t.get("transactionCounter", {}).get("acquisitions"),
            "trades": t.get("transactionCounter", {}).get("trades"),
            "roster": entries,
        })

    games = []
    for m in sched["schedule"]:
        g = {"week": m["matchupPeriodId"], "playoff": m.get("playoffTierType") not in (None, "NONE"),
             "home": m["home"]["teamId"], "home_pts": m["home"].get("totalPoints")}
        if "away" in m:
            g.update(away=m["away"]["teamId"], away_pts=m["away"].get("totalPoints"))
        games.append(g)

    transactions = [{"type": x.get("type"), "status": x.get("status"), "team": x.get("teamId"),
                     "bid": x.get("bidAmount"), "date": x.get("proposedDate"),
                     "items": [{"type": i["type"], "player": i["playerId"],
                                "from": i.get("fromTeamId"), "to": i.get("toTeamId")} for i in x.get("items", [])]}
                    for x in tx.get("transactions", []) if x.get("type") != "LINEUP"]

    free_agents = [player_row(p) for p in fa["players"]]

    everyone = [p for t in teams for p in t["roster"]] + free_agents
    stats = player_stats(name, [p["id"] for p in everyone])
    for p in everyone:
        p["stats"] = stats.get(p["id"], {})

    # Player availability map: every player we know about -> where he lives.
    avail = {}
    for t in teams:
        for p in t["roster"]:
            avail[p["id"]] = {"name": p["name"], "status": "IR" if p["slot"] == "IR" else "ROSTERED", "team_id": t["id"]}
    for p in free_agents:
        avail.setdefault(p["id"], {"name": p["name"], "status": "FREE_AGENT_OR_WAIVER", "team_id": None})

    snap = {"refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "my_team_id": C.LEAGUES[name]["my_team_id"],
            "settings": build_settings(base), "teams": teams, "schedule": games,
            "transactions": transactions, "free_agents": free_agents, "availability": avail}
    out = DATA / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1))
    return snap


def summarize(name, snap):
    s = snap["settings"]
    print(f"\n=== {s['name']} ({name}) — {s['num_teams']} teams, week {s['current_week']}, "
          f"refreshed {snap['refreshed_at']} ===")
    print("lineup:", s["lineup_slots"], "| scoring:", s["scoring_rank_type"],
          "| waivers:", s["acquisition"]["acquisitionType"],
          "| FAAB:", s["acquisition"]["acquisitionBudget"] if s["acquisition"]["isUsingAcquisitionBudget"] else "off",
          "| trade deadline:", time.strftime("%Y-%m-%d", time.gmtime(s["trade"]["deadlineDate"] / 1000)))
    sc = s["schedule"]
    print("reg season weeks:", sc["matchupPeriodCount"], "| playoff teams:", sc.get("playoffTeamCount"))
    for t in sorted(snap["teams"], key=lambda t: (-t["wins"], -t["points_for"])):
        me = " <== ME" if t["id"] == snap["my_team_id"] else ""
        print(f"  {t['id']:>2} {t['name'][:28]:<28} {t['wins']}-{t['losses']}-{t['ties']}  PF {t['points_for']:>7}  "
              f"roster {len(t['roster'])}{me}")
    print(f"  {len(snap['transactions'])} transactions, {len(snap['free_agents'])} free agents tracked, "
          f"{len(snap['availability'])} players mapped")


if __name__ == "__main__":
    for lg in sys.argv[1:] or C.LEAGUES:
        summarize(lg, ingest(lg))
