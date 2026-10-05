"""Live ESPN data via the community `espn-api` package.

NOTE: written against the documented espn-api interface but not yet run
against a real league (the build sandbox cannot reach ESPN). Expect to tune
field names on first live run; failures are surfaced in the dashboard.
"""
from .models import Player

_POS = {"D/ST": "DST", "DST": "DST", "PK": "K", "K": "K"}


def _to_player(p, slot: str = "") -> Player:
    pos = _POS.get(getattr(p, "position", ""), getattr(p, "position", ""))
    proj = getattr(p, "projected_points", None)
    if proj is None or proj == float("inf"):
        proj = 0.0
    status = (getattr(p, "injuryStatus", "") or "ACTIVE").upper().replace(" ", "_")
    if status in ("NONE", "NORMAL", ""):
        status = "ACTIVE"
    return Player(
        name=p.name, pos=pos, team=getattr(p, "proTeam", ""), proj=float(proj),
        status=status, slot=getattr(p, "lineupSlot", slot),
    )


def connect(league_id: int, year: int, espn_s2: str, swid: str):
    from espn_api.football import League
    return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)


def my_roster(league, team_id: int) -> list[Player]:
    team = next(t for t in league.teams if t.team_id == team_id)
    return [_to_player(p) for p in team.roster]


def this_week_opponent(league, team_id: int) -> list[Player]:
    week = league.current_week
    for m in league.box_scores(week):
        for mine, theirs in ((m.home_team, m.away_team), (m.away_team, m.home_team)):
            if getattr(mine, "team_id", None) == team_id:
                lineup = m.away_lineup if mine is m.home_team else m.home_lineup
                return [_to_player(p) for p in lineup if p.slot_position not in ("BE", "IR")]
    return []


def free_agents(league, size: int = 50) -> list[Player]:
    return [_to_player(p) for p in league.free_agents(size=size)]
