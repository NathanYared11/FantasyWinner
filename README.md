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

## Roadmap
- [x] Phase 1: league rules, PPR scoring engine, lineup optimizer, win probability, dashboard shell
- [ ] Phase 1b: verify live ESPN connection (needs network access and your cookies)
- [ ] Phase 2: waiver wire ranking, trade analyzer
- [ ] Phase 3: season/playoff simulator, draft assistant
- [ ] Phase 4: Vegas lines, weather, injury alerts, hosting on Streamlit Cloud

Run tests with `python -m pytest`.
