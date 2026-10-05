# FantasyWinner
Tool to win fantasy

## Live dashboard
Open `index.html` in a browser (or `python3 -m http.server` and visit localhost:8000).
It polls ESPN's public NFL scoreboard feed and refreshes automatically (15/30/60s), with
Live/Upcoming/Final filters and a team search. If the feed is unreachable it falls back to sample data.

## League intelligence (ESPN + nflverse)
Needs `ESPN_S2`, `ESPN_SWID` and the `LEAGUE_*` ids from `fantasy/config.py` in the environment.

    pip install -r requirements.txt
    python -m fantasy.ingest cuzff legoat     # 1. snapshot ESPN leagues -> data/<league>/snapshot.json
    python -m fantasy.analyze cuzff legoat    # 2. power rankings, needs, market map -> report.md
    python -m fantasy.simulate cuzff legoat   # 3. Monte Carlo odds + waiver what-ifs -> odds.md

`data/` is gitignored (rosters, snapshots, cached nflverse files). Usage, bye weeks, Vegas lines and
weather come from nflverse; PFF/FantasyPros/PFR/Sleeper are not reachable from the sandbox.
