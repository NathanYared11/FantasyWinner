from fantasywinner.leagues import LEAGUES, STARTERS
from fantasywinner.models import Player
from fantasywinner.optimizer import optimize_lineup
from fantasywinner.sample_data import sample_opponent, sample_roster
from fantasywinner.scoring import score_dst, score_player
from fantasywinner.winprob import win_probability

S = LEAGUES["legoat"].scoring


def test_ppr_receiver():
    # 8 rec, 100 yds, 1 TD = 8 + 10 + 6
    assert score_player({"rec": 8, "rec_yd": 100, "rec_td": 1}, S) == 24.0


def test_qb_line():
    # 300 yds (12) + 2 TD (8) + 1 INT (-2) + 20 rush yds (2) = 20
    assert score_player({"pass_yd": 300, "pass_td": 2, "int": 1, "rush_yd": 20}, S) == 20.0


def test_kicker_and_league_difference():
    k = {"pat": 2, "fg_40_49": 1, "pat_miss": 1}
    assert score_player(k, LEAGUES["legoat"].scoring) == 5.0
    assert score_player(k, LEAGUES["cuzff"].scoring) == 6.0  # no PAT-miss penalty


def test_dst_gap_buckets_score_zero():
    # 20 pts allowed (0) and 320 yds (0) + 3 sacks
    assert score_dst({"pts_allowed": 20, "yds_allowed": 320, "sack": 3}, S) == 3.0
    assert score_dst({"pts_allowed": 0, "yds_allowed": 90}, S) == 10.0


def test_optimizer_skips_out_players_and_fills_flex():
    best, _ = optimize_lineup(sample_roster(), STARTERS)
    names = {p.name for p in best}
    assert "Demo WR Two" not in names  # OUT
    assert len(best) == 9
    assert "Demo RB Three" in names  # 12.8 beats WR Four for FLEX? RB Three is RB2/FLEX


def test_win_prob_sane():
    wp = win_probability(optimize_lineup(sample_roster(), STARTERS)[0], sample_opponent())
    assert 0 < wp["win_pct"] < 1


def test_waiver_and_trade_and_season():
    from fantasywinner.sample_data import sample_free_agents, sample_league, sample_season
    from fantasywinner.season import round_robin, simulate_season
    from fantasywinner.trade import evaluate_trade, find_trades
    from fantasywinner.waiver import waiver_targets

    lg = LEAGUES["cuzff"]
    me = sample_roster()
    t = waiver_targets(me, sample_free_agents(), lg)
    assert t and all(r["gain"] >= -1e-9 for r in t[:3])

    others = {k: v for k, v in sample_league().items() if k != "You"}
    for r in find_trades(me, others, lg):
        assert r["my_gain"] > 0.5 and r["their_gain"] > 0.5
    res = evaluate_trade(me, others["Team 2"], [], [], lg)
    assert res["my_gain"] == 0 and res["their_gain"] == 0

    teams, sched = sample_season()
    sim = simulate_season(teams, sched, lg)
    assert abs(sum(v["playoff"] for v in sim.values()) - lg.playoff_teams) < 1e-6
    assert abs(sum(v["bye"] for v in sim.values()) - lg.byes) < 1e-6
    assert all(len(w) == 6 for w in round_robin(list(teams), 14))


def test_byes():
    assert LEAGUES["legoat"].byes == 1 and LEAGUES["cuzff"].byes == 2
