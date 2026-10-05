# FantasyWinner
Tool to win fantasy

## Live dashboard
Open `index.html` in a browser (or `python3 -m http.server` and visit localhost:8000).
It polls ESPN's public NFL scoreboard feed and refreshes automatically (15/30/60s), with
Live/Upcoming/Final filters and a team search. If the feed is unreachable it falls back to sample data.
