# Projection backtest (nflverse PPR; fantasy-relevant players, weeks 4-17)

Tuned on 2024 (2167 player-weeks); reported on held-out 2025 (2146 player-weeks).

## Held-out 2025
- season-to-date avg (baseline): RMSE 7.68 | MAE 5.95 | bias +0.43 | RMSE vs next-4-wk avg 5.45 | weekly rank-corr 0.361
- last-3 avg (baseline): RMSE 8.21 | MAE 6.32 | bias +0.48 | RMSE vs next-4-wk avg 6.08 | weekly rank-corr 0.328
- prior-year ppg (baseline): RMSE 8.27 | MAE 6.54 | bias +0.32 | RMSE vs next-4-wk avg 6.14 | weekly rank-corr 0.183
- **my blend (tuned on 2024)**: RMSE 7.51 | MAE 5.83 | bias +0.38 | RMSE vs next-4-wk avg 5.20 | weekly rank-corr 0.394

## Ablations on 2025 (tuned blend, one piece removed)
- usage trend off: RMSE 7.51 | MAE 5.84 | bias +0.38 | RMSE vs next-4-wk avg 5.21
- game environment off: RMSE 7.51 | MAE 5.85 | bias +0.29 | RMSE vs next-4-wk avg 5.13
- wind off: RMSE 7.51 | MAE 5.84 | bias +0.39 | RMSE vs next-4-wk avg 5.21
- opponent matchup off: RMSE 7.51 | MAE 5.84 | bias +0.38 | RMSE vs next-4-wk avg 5.20
- prior season off: RMSE 7.68 | MAE 5.93 | bias +0.53 | RMSE vs next-4-wk avg 5.51

## Final blend (refit on 2024+2025)

```json
{
 "K": 3,
 "decay": 0.9,
 "mix": 0.8,
 "lam": 0.7,
 "usage": 0.15,
 "env": {
  "QB": 0.2,
  "RB": 0.2,
  "WR": 0,
  "TE": 0
 },
 "wind": 0.9,
 "opp": {
  "QB": 0,
  "RB": 0,
  "WR": 0,
  "TE": 0.3
 },
 "bias": {
  "QB": 0.9762,
  "RB": 0.9994,
  "WR": 0.9815,
  "TE": 1.0559
 }
}
```

## Outcome distribution: actual / predicted, per position (empirical, drives floor/ceiling and the simulation)

- QB: P10 0.33x, median 0.98x, P90 1.63x of projection; sd/mean 0.491 (n=643)
- RB: P10 0.28x, median 0.87x, P90 1.84x of projection; sd/mean 0.674 (n=1130)
- WR: P10 0.22x, median 0.88x, P90 1.98x of projection; sd/mean 0.702 (n=1744)
- TE: P10 0.23x, median 0.87x, P90 1.93x of projection; sd/mean 0.734 (n=796)

## Availability, relevant players 2023-25 (non-bye weeks)

P(plays) by injury-report status that week: Doubtful 2% (n=61), None 98% (n=1264), Not listed 84% (n=5737), Out 0% (n=330), Questionable 71% (n=498)

P(plays k weeks ahead | healthy and played now): k=1: 94%, k=10: 83%, k=11: 83%, k=2: 91%, k=3: 90%, k=4: 89%, k=5: 87%, k=6: 86%, k=7: 85%, k=8: 85%, k=9: 84%

P(plays k weeks ahead | listed Out now): k=1: 36%, k=2: 57%, k=3: 68%, k=4: 75%, k=5: 76%, k=6: 78%