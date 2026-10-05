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
