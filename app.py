import os

import pandas as pd
import streamlit as st

from fantasywinner import espn_client
from fantasywinner.leagues import LEAGUES
from fantasywinner.optimizer import lineup_changes, optimize_lineup
from fantasywinner.sample_data import (sample_free_agents, sample_league, sample_opponent,
                                       sample_roster, sample_season)
from fantasywinner.season import simulate_season
from fantasywinner.trade import evaluate_trade, find_trades
from fantasywinner.waiver import waiver_targets
from fantasywinner.winprob import strategy_hint, win_probability

st.set_page_config(page_title="FantasyWinner", page_icon="🏈", layout="wide")


def secret(key, default=None):
    """Read from Streamlit secrets, falling back to environment variables
    (ESPN_S2, ESPN_SWID, TEAM_LEGOAT, TEAM_CUZFF) for cloud setups."""
    try:
        return st.secrets[key]
    except Exception:
        pass
    env = {"espn_s2": "ESPN_S2", "SWID": "ESPN_SWID"}.get(key)
    return os.environ.get(env, default) if env else default


def team_for(league_key):
    try:
        return st.secrets["teams"][league_key]
    except Exception:
        return os.environ.get(f"TEAM_{league_key.upper()}")


@st.cache_data(ttl=300, show_spinner="Loading from ESPN...")
def load_live(league_id, team_id, s2, swid):
    league = espn_client.connect(league_id, 2026, s2, swid)
    teams, sched = espn_client.season_snapshot(league, 14)
    return dict(
        roster=espn_client.my_roster(league, team_id),
        opp=espn_client.this_week_opponent(league, team_id),
        free=espn_client.free_agents(league),
        others=espn_client.all_rosters(league, team_id),
        teams=teams, sched=sched, me=espn_client.my_team_name(league, team_id))


# ---- sidebar ---------------------------------------------------------------
st.sidebar.title("🏈 FantasyWinner")
key = st.sidebar.radio("League", list(LEAGUES), format_func=lambda k: LEAGUES[k].name)
lg = LEAGUES[key]
s2, swid = secret("espn_s2"), secret("SWID")
team_id = team_for(key)
live = bool(s2 and swid and team_id)
st.sidebar.caption("🟢 Live ESPN data" if live else "🟡 Demo mode (sample data). Add ESPN cookies to go live.")
with st.sidebar.expander("League rules"):
    st.write(f"**{lg.teams} teams**, PPR, {lg.playoff_teams} make playoffs")
    st.write(f"Waivers: {lg.waiver_order}")
    st.write(f"Trade deadline: {lg.trade_deadline}")
    st.caption(lg.notes)

others_all = sample_league()
teams_s, sched_s = sample_season()
data = dict(roster=sample_roster(), opp=sample_opponent(), free=sample_free_agents(),
            others={k: v for k, v in others_all.items() if k != "You"},
            teams=teams_s, sched=sched_s, me="You")
if live:
    try:
        data = load_live(lg.league_id, int(team_id), s2, swid)
    except Exception as e:
        st.error(f"Couldn't load ESPN data, showing demo instead. ({e})")
roster, opp, free = data["roster"], data["opp"], data["free"]

st.title(lg.name)
tab_week, tab_waiver, tab_trade, tab_season = st.tabs(
    ["📅 This Week", "🧲 Waiver Wire", "🔄 Trades", "📈 Season"])

# ---- This Week --------------------------------------------------------------
with tab_week:
    current = [p for p in roster if p.slot not in ("BE", "IR", "")] or roster
    best, bench = optimize_lineup(roster, lg.starters)
    wp_best = win_probability(best, opp)
    wp_now = win_probability(current, opp) if current is not roster else wp_best

    c1, c2, c3 = st.columns(3)
    c1.metric("Win probability (optimal lineup)", f"{wp_best['win_pct']:.0%}",
              f"{wp_best['win_pct'] - wp_now['win_pct']:+.0%} vs current lineup")
    c2.metric("Your projection", f"{wp_best['my_proj']:.1f}",
              f"likely {wp_best['my_range'][0]:.0f} to {wp_best['my_range'][1]:.0f}")
    c3.metric("Opponent projection", f"{wp_best['opp_proj']:.1f}")
    st.info(strategy_hint(wp_best["win_pct"]))

    changes = lineup_changes(current, best)
    if changes:
        st.subheader("Recommended changes")
        for c in changes:
            st.write("• " + c)
    else:
        st.success("Your current lineup is already optimal.")

    def table(players):
        return pd.DataFrame([{"Player": p.name, "Pos": p.pos, "Team": p.team, "Opp": p.opp,
                              "Proj": round(p.proj, 1), "Floor": round(p.floor, 1),
                              "Ceiling": round(p.ceiling, 1), "Status": p.status} for p in players])

    st.subheader("Best lineup")
    st.dataframe(table(best), hide_index=True, width="stretch")
    st.subheader("Bench")
    st.dataframe(table(bench), hide_index=True, width="stretch")

# ---- Waiver wire ----------------------------------------------------------------
with tab_waiver:
    st.caption(f"Waivers: {lg.waiver_order}")
    targets = waiver_targets(roster, free, lg)
    if not targets:
        st.info("No free agents found.")
    rows = [{"Add": t["add"].name, "Pos": t["add"].pos, "Proj": round(t["add"].proj, 1),
             "Drop": t["drop"].name, "Lineup gain": t["gain"], "Depth gain": t["depth"],
             "Buzz %": t["add"].trend, "Advice": t["advice"]} for t in targets]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"Lineup gain": st.column_config.NumberColumn(help="Points your best lineup gains this week")})
    if lg.key == "cuzff":
        st.warning("Cuz FF priority never resets: it moves to last after each claim. "
                   "Spend it only on big upgrades.")

# ---- Trades -------------------------------------------------------------------
with tab_trade:
    st.subheader("Trade finder")
    st.caption("1-for-1 swaps that improve both lineups, so they're likely to be accepted.")
    found = find_trades(roster, data["others"], lg)
    if found:
        st.dataframe(pd.DataFrame([{"Team": f["team"], "You give": f"{f['give'].name} ({f['give'].pos})",
                                    "You get": f"{f['get'].name} ({f['get'].pos})",
                                    "Your gain": f["my_gain"], "Their gain": f["their_gain"]} for f in found]),
                     hide_index=True, width="stretch")
    else:
        st.info("No mutually beneficial 1-for-1 trades right now.")

    st.subheader("Trade analyzer")
    partner = st.selectbox("Trade with", list(data["others"]))
    theirs = data["others"][partner]
    give = st.multiselect("You give", [p.name for p in roster])
    get = st.multiselect("You get", [p.name for p in theirs])
    if give and get:
        res = evaluate_trade(roster, theirs, [p for p in roster if p.name in give],
                             [p for p in theirs if p.name in get], lg)
        a, b = st.columns(2)
        a.metric("Your lineup change", f"{res['my_gain']:+.1f} pts/week")
        b.metric("Their lineup change", f"{res['their_gain']:+.1f} pts/week")
        st.info(res["verdict"])
        st.caption(f"Trade review: league votes can veto it ({'7' if lg.key == 'legoat' else '6'} needed). "
                   f"Deadline: {lg.trade_deadline}.")

# ---- Season ---------------------------------------------------------------------
with tab_season:
    me = data["me"]

    @st.cache_data(ttl=300)
    def run_sim(key, teams, sched, force=None):
        return simulate_season(teams, sched, LEAGUES[key], force=force)

    sim = run_sim(lg.key, data["teams"], data["sched"])
    mine = sim[me]
    win_sim = run_sim(lg.key, data["teams"], data["sched"], (me, True))[me]
    loss_sim = run_sim(lg.key, data["teams"], data["sched"], (me, False))[me]
    c1, c2, c3 = st.columns(3)
    c1.metric("Make playoffs", f"{mine['playoff']:.0%}")
    c2.metric("Earn a first-round bye", f"{mine['bye']:.0%}", help=f"Top {lg.byes} seed(s) skip round 1")
    c3.metric("Projected wins", f"{mine['avg_wins']:.1f} of 14")
    st.info(f"This week's game is worth {win_sim['playoff'] - loss_sim['playoff']:.0%} of playoff odds: "
            f"{win_sim['playoff']:.0%} if you win, {loss_sim['playoff']:.0%} if you lose.")
    table_rows = sorted(({"Team": t, "Wins now": data["teams"][t]["wins"],
                          "Proj wins": round(v["avg_wins"], 1), "Playoffs": v["playoff"], "Bye": v["bye"]}
                         for t, v in sim.items()), key=lambda r: -r["Playoffs"])
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch",
                 column_config={"Playoffs": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                                "Bye": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})
    st.caption(f"{lg.playoff_teams} of {lg.teams} teams make the playoffs; seeding tiebreaker is total points for. "
               f"Trade deadline {lg.trade_deadline}.")
