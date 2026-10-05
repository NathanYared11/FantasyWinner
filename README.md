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
