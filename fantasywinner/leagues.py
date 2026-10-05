"""Rules for each of your leagues, copied from the ESPN settings pages."""
from dataclasses import dataclass, field

# Scoring shared by both leagues (full PPR, 4pt pass TD, -2 INT, -2 fumble lost).
BASE_SCORING = {
    "pass_yd": 0.04, "pass_td": 4, "int": -2, "two_pt": 2,
    "rush_yd": 0.1, "rush_td": 6,
    "rec": 1, "rec_yd": 0.1, "rec_td": 6,
    "fum_lost": -2, "ret_td": 6,
    "pat": 1, "fg_0_39": 3, "fg_40_49": 4, "fg_50_59": 5, "fg_60": 6,
    "fg_miss": -1,
    # D/ST
    "sack": 1, "def_int": 2, "fum_rec": 2, "safety": 2, "blk": 2, "def_td": 6,
}

# D/ST buckets: (max_value_inclusive, points). Gaps in ESPN's table score 0.
POINTS_ALLOWED = [(0, 5), (6, 4), (13, 3), (17, 1), (27, 0), (34, -1), (45, -3), (10**9, -5)]
YARDS_ALLOWED = [(99, 5), (199, 3), (299, 2), (349, 0), (399, -1), (449, -3),
                 (499, -5), (549, -6), (10**9, -7)]

STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1}
FLEX_ELIGIBLE = ("RB", "WR", "TE")


@dataclass(frozen=True)
class League:
    key: str
    name: str
    league_id: int
    teams: int
    playoff_teams: int
    waiver_order: str
    trade_deadline: str
    scoring: dict = field(default_factory=lambda: dict(BASE_SCORING))
    starters: dict = field(default_factory=lambda: dict(STARTERS))
    bench: int = 7
    ir: int = 1
    notes: str = ""


LEAGUES = {
    "legoat": League(
        key="legoat", name="LeGoat Fantasy League", league_id=223249425,
        teams=12, playoff_teams=7,
        waiver_order="Resets each week to inverse standings",
        trade_deadline="Dec 16, 2026",
        scoring={**BASE_SCORING, "pat_miss": -1},
        notes="7 playoff teams: seed #1 gets a bye. Matchup tiebreaker: most bench points.",
    ),
    "cuzff": League(
        key="cuzff", name="Cuz FF", league_id=160739148,
        teams=12, playoff_teams=6,
        waiver_order="Move to last after a claim, never reset",
        trade_deadline="Nov 11, 2026",
        scoring={**BASE_SCORING, "pat_miss": 0},
        notes="6 playoff teams: seeds #1-2 get a bye. No matchup tiebreaker. "
              "Waiver priority is precious: it only resets by using it.",
    ),
}
