"""League registry. League IDs and ESPN credentials come from environment variables."""
import os
from pathlib import Path

SEASON = 2026
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# name -> (env var holding the ESPN league ID, my ESPN team ID)
LEAGUES = {
    "cuzff":  {"id_env": "LEAGUE_CUZFF",  "my_team_id": 2},   # drag yo nutz
    "legoat": {"id_env": "LEAGUE_LEGOAT", "my_team_id": 2},   # Hail Heinicke
}

POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
LINEUP_SLOTS = {0: "QB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE", 7: "OP",
                16: "D/ST", 17: "K", 20: "BE", 21: "IR", 23: "FLEX"}
PRO_TEAMS = {
    0: "FA", 1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
    17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}


def credentials():
    return os.environ["ESPN_S2"], os.environ["ESPN_SWID"]


def league_id(name):
    return os.environ[LEAGUES[name]["id_env"]]
