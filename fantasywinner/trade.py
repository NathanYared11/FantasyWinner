"""Trade analyzer and trade-partner finder, based on lineup impact for both sides."""
from .leagues import League
from .models import Player
from .waiver import lineup_total


def _apply(roster, give, get):
    gone = {p.name for p in give}
    return [p for p in roster if p.name not in gone] + list(get)


def evaluate_trade(mine, theirs, give, get, league: League) -> dict:
    my_before = lineup_total(mine, league.starters)
    their_before = lineup_total(theirs, league.starters)
    my_gain = lineup_total(_apply(mine, give, get), league.starters) - my_before
    their_gain = lineup_total(_apply(theirs, get, give), league.starters) - their_before
    if my_gain > 0.5 and their_gain > 0.5:
        verdict = "Win-win: both lineups improve, so it should get accepted."
    elif my_gain > 0.5 and their_gain <= 0.5:
        verdict = "Favors you. They may decline; check what else they get out of it."
    elif my_gain <= 0.5 and their_gain > 0.5:
        verdict = "Favors them. Don't do it unless you need depth."
    else:
        verdict = "Neither lineup moves much; it only matters for depth."
    return {"my_gain": round(my_gain, 1), "their_gain": round(their_gain, 1), "verdict": verdict}


def find_trades(mine, others: dict, league: League, top: int = 10) -> list[dict]:
    """1-for-1 swaps that help both teams, best for you first."""
    results = []
    for team, roster in others.items():
        for give in mine:
            for get in roster:
                if not (give.available and get.available) or give.pos == get.pos == "K":
                    continue
                r = evaluate_trade(mine, roster, [give], [get], league)
                if r["my_gain"] > 0.5 and r["their_gain"] > 0.5:
                    results.append({"team": team, "give": give, "get": get, **r})
    results.sort(key=lambda r: (r["my_gain"], r["their_gain"]), reverse=True)
    seen, unique = set(), []
    for r in results:  # keep only the best target per (team, player you give)
        k = (r["team"], r["give"].name)
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return unique[:top]
