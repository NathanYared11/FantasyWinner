import pandas as pd
import streamlit as st

from fantasywinner import espn_client
from fantasywinner.leagues import LEAGUES
from fantasywinner.optimizer import lineup_changes, optimize_lineup
from fantasywinner.sample_data import sample_opponent, sample_roster
from fantasywinner.winprob import strategy_hint, win_probability

st.set_page_config(page_title="FantasyWinner", page_icon="🏈", layout="wide")


def secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default


@st.cache_data(ttl=300, show_spinner="Loading from ESPN...")
def load_live(league_id, team_id, s2, swid):
    league = espn_client.connect(league_id, 2026, s2, swid)
    return (espn_client.my_roster(league, team_id),
            espn_client.this_week_opponent(league, team_id),
            espn_client.free_agents(league))


# ---- sidebar ---------------------------------------------------------------
st.sidebar.title("🏈 FantasyWinner")
key = st.sidebar.radio("League", list(LEAGUES), format_func=lambda k: LEAGUES[k].name)
lg = LEAGUES[key]
s2, swid = secret("espn_s2"), secret("SWID")
team_id = (secret("teams") or {}).get(key)
live = bool(s2 and swid and team_id)
st.sidebar.caption("🟢 Live ESPN data" if live else "🟡 Demo mode (sample data). Add ESPN cookies to go live.")
with st.sidebar.expander("League rules"):
    st.write(f"**{lg.teams} teams**, PPR, {lg.playoff_teams} make playoffs")
    st.write(f"Waivers: {lg.waiver_order}")
    st.write(f"Trade deadline: {lg.trade_deadline}")
    st.caption(lg.notes)

roster, opp, free = sample_roster(), sample_opponent(), []
if live:
    try:
        roster, opp, free = load_live(lg.league_id, int(team_id), s2, swid)
    except Exception as e:
        st.error(f"Couldn't load ESPN data, showing demo instead. ({e})")

st.title(lg.name)
tab_week, tab_waiver, tab_trade, tab_season, tab_draft = st.tabs(
    ["📅 This Week", "🧲 Waiver Wire", "🔄 Trades", "📈 Season", "🎯 Draft"])

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

# ---- Placeholders for later phases -------------------------------------------
for tab, text in (
    (tab_waiver, "Free-agent rankings by rest-of-season value, with who to drop. Phase 2."),
    (tab_trade, "Trade analyzer and partner finder. Phase 2."),
    (tab_season, "Playoff odds, schedule strength and bye planning. Phase 3."),
    (tab_draft, "Live draft assistant and value board. Phase 3."),
):
    with tab:
        st.info("Coming soon: " + text)
