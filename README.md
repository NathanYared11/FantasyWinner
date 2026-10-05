# FantasyWinner
Tool to win fantasy

## ESPN connection

`src/espn.js` is a dependency-free client for ESPN's fantasy API (football, basketball, baseball, hockey).

```sh
export ESPN_LEAGUE_ID=123456
export ESPN_SEASON=2026          # optional, defaults to current year
export ESPN_SPORT=football       # football|basketball|baseball|hockey
# private leagues only (browser cookies from fantasy.espn.com):
export ESPN_S2=...
export ESPN_SWID='{...}'

npm run espn -- teams        # also: scoreboard [week], players [limit], league
npm test
```

## Projection model

- `src/providers/sleeper.js`: second data source (Sleeper's public API) so no single feed is a point of failure.
- `src/model/projection.js`: blends sources, adds recency-weighted form with shrinkage toward the position mean, applies injury and matchup adjustments, and returns an ~80% interval.
- `src/model/backtest.js`: MAE/RMSE/interval coverage, inverse-error source weighting, and a walk-forward backtest (no lookahead). Feed it past weeks of `{projections, actual}` rows to see whether changes actually help.

## Learned model (nflverse history)

```sh
scripts/fetch-data.sh            # nflverse weekly stats, injuries, schedules + Vegas lines (2019+)
node scripts/train.js            # walk-forward backtest vs baselines, saves models/ridge.json
node scripts/predict.js 2026 5   # projections for a week (defaults to next unplayed week)
```

Per-position ridge regression predicting PPR points from only prior games: recency-weighted points, usage
(carries+targets / attempts), target and air-yard share, volatility, rest gap, Vegas implied team total and
spread, home/away, injury report status, and points the opponent defense has recently allowed to the position.

Out-of-sample walk-forward results (2024+, each week predicted from earlier weeks only; lambda tuned on 2023):

| fantasy-relevant players | MAE | RMSE | weekly rank corr |
|---|---|---|---|
| 16-game mean | 6.05 | 7.62 | 0.43 |
| recency-weighted | 6.02 | 7.61 | 0.44 |
| ridge model | 5.81 | 7.39 | 0.48 |

Caveats: evaluation rows only include players who actually played, so it does not price in surprise inactives.
Weekly NFL scoring is very noisy, so expect a few percent of error reduction, not a crystal ball. Sleeper and
ESPN projections are not in the backtest (no historical copies are available); once you log them weekly,
`src/model/backtest.js` can fit blend weights between them and this model.

## Kickers, defenses, lineups and waivers

- **K and D/ST** are projected by the same model. Their points are derived from nflverse data (FG distance and PATs; sacks, turnovers, TDs, safeties, blocks, and points allowed from the scoreboard) using standard ESPN-style scoring, so a league with custom scoring will differ. The model lowers error versus the baselines for both, but week-to-week ranking skill is low (rank corr about 0.10): treat them as streaming picks.
- `src/lineup.js`: exact lineup optimizer for any slot layout (FLEX, SUPERFLEX, ...), with `mean`, `floor` (safe) and `ceiling` (need a big week) modes, close-call detection, and waiver-wire gain (points a free agent adds to your best lineup).
- `src/espn-roster.js`: converts ESPN roster/settings payloads and matches players to projections by name and position.

```sh
# Live ESPN team (find your team id in the league URL, ?teamId=N)
ESPN_LEAGUE_ID=123456 ESPN_TEAM_ID=3 ESPN_S2=... ESPN_SWID='{...}' node scripts/lineup.js 5 floor
# Offline with your own roster file
node scripts/lineup.js 5 mean --roster roster.json
```

The live ESPN path (`espn.js` plus the ID mappings in `espn-roster.js`) is untested against ESPN's servers: they are not reachable from the development sandbox. The optimizer, matching and projection code are covered by tests.

## Dashboard and projection log

- `node scripts/build-dashboard.js [season] [week]` builds `dashboard/dist/index.html` (projections table, roster-to-lineup tool with waiver adds, model accuracy). Rebuild it each week after `scripts/fetch-data.sh`.
- `node scripts/log-projections.js` snapshots this week's projections from the model and Sleeper into `logs/` (run it before games; commit the files). After the games, `node scripts/blend-report.js` scores each source and the equal/tuned blends against actual points, so you can see whether blending Sleeper with the model beats either alone.

### Using your own team

`node scripts/build-dashboard.js` bakes your team into the dashboard. In order of preference:

1. Live ESPN: `ESPN_LEAGUE_ID=… ESPN_TEAM_ID=… [ESPN_S2=… ESPN_SWID=…] node scripts/build-dashboard.js` (uses your league's lineup slots and real free agents).
2. `dashboard/roster.json` (git-ignored): `{ "team": "Team name", "roster": [{"name": "Josh Allen", "pos": "QB"}, ...], "slots": {"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1,"DST":1,"K":1}, "free": ["optional list of available players"] }`.
3. Otherwise it shows a clearly labelled example roster. You can also paste a roster into the page itself; it is saved in your browser only.

## League analysis: team needs and trades

Every team's roster is valued over the rest of the season (default through week 14; set `FW_LAST_WEEK`). Each remaining week is projected by the model, with byes and opponents from the schedule, then each team's best lineup is re-optimized week by week. That gives:

- **Power rankings**: projected lineup points per week for every team.
- **What your team needs**: your rank at each position, and how many points per week a solid starter or a star would add to your lineup.
- **Trade ideas**: 1-for-1 and 2-for-1 deals where *both* teams improve, graded A+ to F by your gain.
- **Trade grader**: pick players on each side (in the dashboard's Trades tab, or `node scripts/league.js grade --with 3 --give "A,B" --get "C"`). It also compares against FantasyCalc's market trade values when that API is reachable.

League source, in order: live ESPN (`ESPN_LEAGUE_ID`, `ESPN_TEAM_ID`, plus `ESPN_S2`/`ESPN_SWID` if private), `dashboard/league.json`, or a simulated example league. `league.json` looks like `{ "teams": [{ "id": 1, "name": "Team", "mine": true, "roster": [{"name": "Josh Allen", "pos": "QB"}] }, ...], "slots": {"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1,"DST":1,"K":1} }`.

Limits: projections assume full PPR; betting lines exist only for the current week, so later weeks use a neutral game environment (opponent defense and byes still count); a player's current injury is applied to this week only, so long-term injuries are not discounted yet; the bench depth credit (10% of a bench player's points) is a rough stand-in for injury insurance.

Several leagues: set `ESPN_LEAGUE=NAME` plus `LEAGUE_NAME=<league id>` and `TEAM_NAME=<team id>` (for example `ESPN_LEAGUE=CUZFF`, `LEAGUE_CUZFF=123`, `TEAM_CUZFF=2`) instead of `ESPN_LEAGUE_ID`/`ESPN_TEAM_ID`. The dashboard builds *every* `LEAGUE_*`/`TEAM_*` pair into one page with a league switcher (the `ESPN_LEAGUE` one opens first and is also what `scripts/league.js` uses). Set `FW_OFFLINE_DEMO=1` to preview the switcher without ESPN access.
