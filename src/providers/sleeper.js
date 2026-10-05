// Sleeper's public, read-only API (no auth). Used as a second source alongside ESPN.
const BASE = "https://api.sleeper.app/v1";
const STATS = "https://api.sleeper.com";

export class SleeperClient {
  constructor({ fetchImpl = fetch } = {}) {
    this.fetch = fetchImpl;
  }
  async get(url) {
    const res = await this.fetch(url, { headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`Sleeper request failed: ${res.status} ${res.statusText}`);
    return res.json();
  }
  players(sport = "nfl") {
    return this.get(`${BASE}/players/${sport}`);
  }
  trending(sport = "nfl", type = "add", hours = 24) {
    return this.get(`${BASE}/players/${sport}/trending/${type}?lookback_hours=${hours}`);
  }
  // Returns { [playerId]: { pts_ppr, ... } } for one week.
  projections(season, week, sport = "nfl") {
    return this.get(`${STATS}/projections/${sport}/${season}/${week}?season_type=regular`);
  }
}
