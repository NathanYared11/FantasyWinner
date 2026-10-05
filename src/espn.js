// Minimal client for ESPN's (unofficial) Fantasy API.
// Private leagues need the `espn_s2` and `SWID` cookies from a logged-in browser session.

const BASE = "https://lksv3.fantasy.espn.com/apis/v3/games";

export const SPORTS = {
  football: "ffl",
  basketball: "fba",
  baseball: "flb",
  hockey: "fhl",
};

// Views accepted by ESPN, e.g. mTeam, mRoster, mMatchup, mSettings, mStandings, kona_player_info.
export class EspnClient {
  constructor({ leagueId, season, sport = "football", espnS2, swid, fetchImpl = fetch } = {}) {
    if (!leagueId) throw new Error("leagueId is required");
    if (!SPORTS[sport]) throw new Error(`unknown sport "${sport}" (use ${Object.keys(SPORTS).join(", ")})`);
    this.leagueId = String(leagueId);
    this.season = season ?? new Date().getFullYear();
    this.sport = SPORTS[sport];
    this.espnS2 = espnS2;
    this.swid = swid;
    this.fetch = fetchImpl;
  }

  url(views = [], params = {}) {
    const u = new URL(`${BASE}/${this.sport}/seasons/${this.season}/segments/0/leagues/${this.leagueId}`);
    for (const v of views) u.searchParams.append("view", v);
    for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
    return u;
  }

  async request(views, params, headers = {}) {
    const cookie = this.espnS2 && this.swid ? `espn_s2=${this.espnS2}; SWID=${this.swid}` : undefined;
    const res = await this.fetch(this.url(views, params), {
      headers: { accept: "application/json", ...(cookie && { cookie }), ...headers },
    });
    if (res.status === 401 || res.status === 403) {
      throw new Error(`ESPN denied access (${res.status}); private leagues need espn_s2 and SWID cookies`);
    }
    if (!res.ok) throw new Error(`ESPN request failed: ${res.status} ${res.statusText}`);
    return res.json();
  }

  league(views = ["mTeam", "mRoster", "mSettings", "mStandings"]) {
    return this.request(views);
  }

  async teams() {
    const data = await this.league(["mTeam", "mRoster"]);
    return data.teams ?? [];
  }

  async scoreboard(week) {
    const data = await this.request(["mMatchup", "mMatchupScore"], week ? { scoringPeriodId: week } : {});
    return week ? (data.schedule ?? []).filter((m) => m.matchupPeriodId === Number(week)) : (data.schedule ?? []);
  }

  // Top available/rostered players; ESPN filters via the x-fantasy-filter header.
  async players({ limit = 50, offset = 0, statusIds } = {}) {
    const filter = {
      players: {
        limit,
        offset,
        sortPercOwned: { sortPriority: 1, sortAsc: false },
        ...(statusIds && { filterStatus: { value: statusIds } }),
      },
    };
    const data = await this.request(["kona_player_info"], {}, { "x-fantasy-filter": JSON.stringify(filter) });
    return data.players ?? [];
  }
}

export function fromEnv(env = process.env, overrides = {}) {
  return new EspnClient({
    leagueId: env.ESPN_LEAGUE_ID,
    season: env.ESPN_SEASON ? Number(env.ESPN_SEASON) : undefined,
    sport: env.ESPN_SPORT || "football",
    espnS2: env.ESPN_S2,
    swid: env.ESPN_SWID,
    ...overrides,
  });
}
