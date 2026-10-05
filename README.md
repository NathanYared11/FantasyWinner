# FantasyWinner

A dashboard for winning two ESPN PPR leagues: **LeGoat Fantasy League** and **Cuz FF**.

## Run it
```
pip install -r requirements.txt
streamlit run app.py
```
With no setup it runs in **demo mode** on fictional sample players.

## Go live with your ESPN data
1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Fill in `espn_s2` and `SWID` (browser cookies on fantasy.espn.com: Chrome > F12 >
   Application > Cookies) and your team number in each league. **Never commit this file.**
3. Restart the app. The sidebar will show "Live ESPN data".

## What's in the dashboard
- **This Week**: best PPR lineup, win probability vs your opponent, safe/risky advice, swap suggestions
- **Waiver Wire**: free agents ranked by real lineup gain, who to drop, league-specific claim advice
  (LeGoat resets waivers weekly; Cuz FF priority never resets, so it warns you before you burn it)
- **Trades**: finder for 1-for-1 swaps that help both teams, plus a trade analyzer
- **Season**: playoff and first-round-bye odds from simulation, and how much this week's game swings them

Drafts for both leagues already happened, so there is no draft tab.

## Environment variables (alternative to secrets.toml)
`ESPN_S2`, `ESPN_SWID`, `TEAM_LEGOAT`, `TEAM_CUZFF`

## Status
Everything runs on demo data. The live ESPN connection (`fantasywinner/espn_client.py`) is
written but untested against real leagues: expect small fixes on first live run.
Next: Vegas lines and weather in projections, injury alerts, hosting.

Run tests with `python -m pytest`.
