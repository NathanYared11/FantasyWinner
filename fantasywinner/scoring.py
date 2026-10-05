"""Turn a raw stat line into fantasy points using a league's scoring rules."""
from .leagues import POINTS_ALLOWED, YARDS_ALLOWED


def _bucket(value, table):
    for limit, pts in table:
        if value <= limit:
            return pts
    return 0


def score_player(stats: dict, s: dict) -> float:
    g = lambda k: stats.get(k, 0)
    pts = (
        g("pass_yd") * s["pass_yd"] + g("pass_td") * s["pass_td"] + g("int") * s["int"]
        + g("rush_yd") * s["rush_yd"] + g("rush_td") * s["rush_td"]
        + g("rec") * s["rec"] + g("rec_yd") * s["rec_yd"] + g("rec_td") * s["rec_td"]
        + g("fum_lost") * s["fum_lost"] + g("two_pt") * s["two_pt"] + g("ret_td") * s["ret_td"]
        + g("pat") * s["pat"] + g("pat_miss") * s.get("pat_miss", 0)
        + g("fg_0_39") * s["fg_0_39"] + g("fg_40_49") * s["fg_40_49"]
        + g("fg_50_59") * s["fg_50_59"] + g("fg_60") * s["fg_60"]
        + g("fg_miss") * s["fg_miss"]
    )
    return round(pts, 2)


def score_dst(stats: dict, s: dict) -> float:
    g = lambda k: stats.get(k, 0)
    pts = (
        g("sack") * s["sack"] + g("def_int") * s["def_int"] + g("fum_rec") * s["fum_rec"]
        + g("safety") * s["safety"] + g("blk") * s["blk"] + g("def_td") * s["def_td"]
        + _bucket(g("pts_allowed"), POINTS_ALLOWED)
        + _bucket(g("yds_allowed"), YARDS_ALLOWED)
    )
    return round(pts, 2)
