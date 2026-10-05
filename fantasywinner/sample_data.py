"""Fictional demo rosters so the dashboard works before ESPN is connected."""
from .models import Player

_ROWS = [
    # name, pos, team, proj, status, opp, slot
    ("Demo QB Alpha", "QB", "AAA", 21.5, "ACTIVE", "vs BBB", "QB"),
    ("Demo QB Backup", "QB", "CCC", 15.0, "ACTIVE", "@ DDD", "BE"),
    ("Demo RB One", "RB", "EEE", 17.2, "ACTIVE", "vs FFF", "RB"),
    ("Demo RB Two", "RB", "GGG", 9.1, "QUESTIONABLE", "@ HHH", "RB"),
    ("Demo RB Three", "RB", "III", 12.8, "ACTIVE", "vs JJJ", "BE"),
    ("Demo RB Four", "RB", "KKK", 7.0, "ACTIVE", "@ LLL", "BE"),
    ("Demo WR One", "WR", "MMM", 16.4, "ACTIVE", "vs NNN", "WR"),
    ("Demo WR Two", "WR", "OOO", 8.0, "OUT", "@ PPP", "WR"),
    ("Demo WR Three", "WR", "QQQ", 13.9, "ACTIVE", "vs RRR", "FLEX"),
    ("Demo WR Four", "WR", "SSS", 12.1, "ACTIVE", "@ TTT", "BE"),
    ("Demo TE One", "TE", "UUU", 11.3, "ACTIVE", "vs VVV", "TE"),
    ("Demo K One", "K", "WWW", 8.2, "ACTIVE", "@ XXX", "K"),
    ("Demo DST One", "DST", "YYY", 7.5, "ACTIVE", "vs ZZZ", "DST"),
]

_OPP = [
    ("Opp QB", "QB", 19.0, "QB"), ("Opp RB A", "RB", 15.0, "RB"), ("Opp RB B", "RB", 11.0, "RB"),
    ("Opp WR A", "WR", 15.5, "WR"), ("Opp WR B", "WR", 12.0, "WR"), ("Opp TE", "TE", 9.0, "TE"),
    ("Opp FLEX", "WR", 11.5, "FLEX"), ("Opp K", "K", 7.8, "K"), ("Opp DST", "DST", 8.0, "DST"),
]


def sample_roster() -> list[Player]:
    return [Player(n, pos, t, pr, st, o, slot=sl) for n, pos, t, pr, st, o, sl in _ROWS]


def sample_opponent() -> list[Player]:
    return [Player(n, pos, "OPP", pr, slot=sl) for n, pos, pr, sl in _OPP]
