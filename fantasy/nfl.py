"""NFL context from nflverse (free, public): usage, bye weeks, Vegas lines, weather.

PFF / FantasyPros / PFR / Sleeper are not reachable from the sandbox (and PFF is paywalled), so
usage comes from nflverse snap counts + weekly player stats instead.

    python -m fantasy.nfl            # refresh the cache
"""
import csv
import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from . import config as C
from . import model as M

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
FILES = {
    "games": "schedules/games.csv",
    "players": "players/players.csv",
    "snaps": f"snap_counts/snap_counts_{C.SEASON}.csv",
    "stats": f"stats_player/stats_player_week_{C.SEASON}.csv",
    "injuries": f"injuries/injuries_{C.SEASON}.csv",
}
ESPN_TO_NFLVERSE = {"WSH": "WAS", "LAR": "LA"}
LEAGUE_AVG_IMPLIED = 22.5
WIND_MPH = 15


def refresh(max_age_h=6):
    """Download nflverse files (skipped if the cache is fresh). Returns the refresh timestamp."""
    DIR.mkdir(parents=True, exist_ok=True)
    stamp = DIR / "refreshed.json"
    if stamp.exists() and time.time() - json.loads(stamp.read_text())["epoch"] < max_age_h * 3600:
        return json.loads(stamp.read_text())["utc"]
    for rel in FILES.values():
        out = subprocess.run(["curl", "-sS", "-m", "180", "-L", "--fail", "-o", str(DIR / Path(rel).name), f"{BASE}/{rel}"],
                             capture_output=True, text=True)
        if out.returncode:
            raise RuntimeError(f"nflverse download failed for {rel}: {out.stderr.strip()}")
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stamp.write_text(json.dumps({"epoch": time.time(), "utc": utc}))
    return utc


def _rows(key):
    with open(DIR / Path(FILES[key]).name, newline="") as f:
        return list(csv.DictReader(f))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class NFL:
    def __init__(self, max_age_h=6):
        self.refreshed_at = refresh(max_age_h)
        self.gsis = {r["espn_id"]: r for r in _rows("players") if r["espn_id"]}
        self.pfr_to_gsis = {r["pfr_id"]: r["gsis_id"] for r in self.gsis.values() if r["pfr_id"]}

        self.games = {}                      # (week, team) -> game dict from that team's perspective
        self.bye = {}
        played_weeks = defaultdict(set)
        for r in _rows("games"):
            if r["season"] != str(C.SEASON) or r["game_type"] != "REG":
                continue
            wk, home, away = int(r["week"]), r["home_team"], r["away_team"]
            spread, total = _num(r["spread_line"]), _num(r["total_line"])   # spread: positive = home favored
            done = r["result"] != ""
            for team, opp, is_home in ((home, away, True), (away, home, False)):
                implied = None
                if spread is not None and total is not None:
                    implied = total / 2 + (spread / 2 if is_home else -spread / 2)
                self.games[(wk, team)] = {
                    "opp": opp, "home": is_home, "done": done, "implied": implied,
                    "opp_implied": (total - implied) if implied is not None else None,
                    "roof": r["roof"], "temp": _num(r["temp"]), "wind": _num(r["wind"]), "date": r["gameday"]}
                played_weeks[team].add(wk)
        for team, wks in played_weeks.items():
            missing = [w for w in range(1, 19) if w not in wks]
            self.bye[team] = missing[0] if missing else None

        # usage: snap share + target/carry share by week
        self.snap = defaultdict(dict)
        for r in _rows("snaps"):
            g = self.pfr_to_gsis.get(r["pfr_player_id"])
            pct = _num(r["offense_pct"])
            if g and pct and pct > 0:
                self.snap[g][int(r["week"])] = pct
        team_t, team_c = defaultdict(float), defaultdict(float)
        stat_rows = [r for r in _rows("stats") if r["season_type"] == "REG"]
        for r in stat_rows:
            team_t[(r["team"], r["week"])] += _num(r["targets"]) or 0
            team_c[(r["team"], r["week"])] += _num(r["carries"]) or 0
        self.share = defaultdict(dict)
        for r in stat_rows:
            t, c = _num(r["targets"]) or 0, _num(r["carries"]) or 0
            tt, tc = team_t[(r["team"], r["week"])], team_c[(r["team"], r["week"])]
            self.share[r["player_id"]][int(r["week"])] = (t / tt if tt else 0, c / tc if tc else 0)
        rows = []
        for r in stat_rows:
            if r["position"] in M.POS and r["opponent_team"]:
                rows.append((int(r["week"]), r["opponent_team"], r["position"], _num(r["fantasy_points_ppr"]) or 0))
        self.matchups = M.Matchups(rows, [(w, t) for (w, t), g in self.games.items() if g["done"]])
        self.report = {}
        for r in _rows("injuries"):
            self.report[r["gsis_id"]] = (int(r["week"]), r["report_status"], r["practice_status"])

    # ---- lookups -------------------------------------------------------------------------------
    def team(self, espn_abbrev):
        return ESPN_TO_NFLVERSE.get(espn_abbrev, espn_abbrev)

    def bye_week(self, espn_abbrev):
        return self.bye.get(self.team(espn_abbrev))

    def game(self, week, espn_abbrev):
        return self.games.get((week, self.team(espn_abbrev)))

    def env_factor(self, pos, espn_abbrev, week):
        """Game-environment multiplier. QB/RB/WR/TE exponents + wind come from the backtest
        (fantasy/params.json); K and D/ST use unvalidated assumptions. 1.0 when no line is posted."""
        g = self.game(week, espn_abbrev)
        if not g or g["implied"] is None:
            return 1.0
        B = M.load_params()["blend"]
        f = 1.0
        windy = g["roof"] == "outdoors" and (g["wind"] or 0) >= WIND_MPH
        if pos in M.POS:
            f = (g["implied"] / LEAGUE_AVG_IMPLIED) ** B["env"].get(pos, 0)
            if windy and pos in ("QB", "WR", "TE"):
                f *= B["wind"]
        elif pos == "K":
            f = (g["implied"] / LEAGUE_AVG_IMPLIED) ** .5 * (.92 if windy else 1)
        elif pos == "D/ST":
            f = (LEAGUE_AVG_IMPLIED / max(g["opp_implied"], 10)) ** .8
        return max(.8, min(1.2, f))

    def opp_factor(self, pos, espn_abbrev, week):
        """Opposing defense's points allowed to the position so far this season (backtest-validated exponent)."""
        g = self.game(week, espn_abbrev)
        e = M.load_params()["blend"]["opp"].get(pos, 0)
        if not g or not e or pos not in M.POS:
            return 1.0
        return max(.85, min(1.15, self.matchups.rel(18, g["opp"], pos) ** e))

    def usage(self, espn_id, pos):
        """Recent-vs-season role. Returns dict and a bounded multiplier (RB/WR/TE only)."""
        g = self.gsis.get(str(espn_id))
        if not g or pos not in ("RB", "WR", "TE"):
            return {}, 1.0
        gid = g["gsis_id"]
        snaps = [v for _, v in sorted(self.snap.get(gid, {}).items())]
        sh = [v for _, v in sorted(self.share.get(gid, {}).items())]
        info = {}
        if sh:
            last3 = sh[-3:]
            info["target_share"] = round(sum(x[0] for x in last3) / len(last3), 3)
            info["carry_share"] = round(sum(x[1] for x in last3) / len(last3), 3)
        mult = 1.0
        if len(snaps) >= 3:
            recent, season = sum(snaps[-2:]) / 2, sum(snaps) / len(snaps)
            info.update(snap_recent=round(recent, 2), snap_season=round(season, 2))
            if season >= .2:
                mult = max(.92, min(1.08, 1 + .3 * (recent / season - 1)))
        rep = self.report.get(gid)
        if rep:
            info["nfl_report"] = f"wk{rep[0]} {rep[1]}/{rep[2]}"
        return info, mult


if __name__ == "__main__":
    n = NFL(max_age_h=0)
    print("nflverse refreshed", n.refreshed_at, "| players mapped:", len(n.gsis), "| games:", len(n.games) // 2)
