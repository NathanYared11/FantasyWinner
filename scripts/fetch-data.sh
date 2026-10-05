#!/usr/bin/env bash
# Downloads open NFL data from nflverse (https://github.com/nflverse/nflverse-data) into ./data
set -u
cd "$(dirname "$0")/.." && mkdir -p data
REL=https://github.com/nflverse/nflverse-data/releases/download
FIRST=${FIRST:-2019}; LAST=${LAST:-$(date +%Y)}
get() { curl -fsSL --retry 3 -m 180 -o "data/$2" "$REL/$1/$2" || { rm -f "data/$2"; echo "skip $2"; }; }
for y in $(seq "$FIRST" "$LAST"); do
  get stats_player "stats_player_week_$y.csv" &
  get injuries "injuries_$y.csv" &
done
get schedules games.csv &
wait
ls data
