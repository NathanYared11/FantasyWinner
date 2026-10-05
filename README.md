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
