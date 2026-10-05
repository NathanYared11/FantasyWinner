// Translate ESPN fantasy payloads into the {name,pos,team} shape the projection tools use.
export const ESPN_POSITIONS = { 1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST" };
// ESPN lineupSlotId -> our slot name (bench=20, IR=21 are not starting slots).
export const ESPN_SLOTS = { 0: "QB", 2: "RB", 3: "WRRB", 4: "WR", 5: "WRRB", 6: "TE", 7: "SUPERFLEX", 16: "DST", 17: "K", 23: "FLEX", 24: "SUPERFLEX" };
export const ESPN_TEAMS = {
  1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND",
  12: "KC", 13: "LV", 14: "LA", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
  22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
};

export const normName = (n) =>
  n.toLowerCase().replace(/[.'’`]/g, "").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "").replace(/[^a-z ]/g, " ").replace(/\s+/g, " ").trim();

export function espnPlayer(entry) {
  const p = entry.playerPoolEntry?.player ?? entry.player ?? entry;
  const pos = ESPN_POSITIONS[p.defaultPositionId];
  const team = ESPN_TEAMS[p.proTeamId];
  if (!pos) return null;
  return { name: pos === "DST" ? `${team} D/ST` : p.fullName, pos, team, espnId: p.id, injuryStatus: p.injuryStatus };
}

// league.settings.rosterSettings.lineupSlotCounts -> { QB: 1, RB: 2, ... }
export function slotsFromSettings(settings) {
  const counts = settings?.rosterSettings?.lineupSlotCounts ?? {};
  const slots = {};
  for (const [id, n] of Object.entries(counts)) if (n > 0 && ESPN_SLOTS[id]) slots[ESPN_SLOTS[id]] = (slots[ESPN_SLOTS[id]] ?? 0) + n;
  return Object.keys(slots).length ? slots : undefined;
}

// Attach model projections to ESPN players by normalized name + position (falls back to name only).
export function attachProjections(players, projections) {
  const byKey = new Map(projections.map((p) => [`${normName(p.name)}|${p.pos}`, p]));
  const byName = new Map(projections.map((p) => [normName(p.name), p]));
  return players.map((pl) => {
    const proj = byKey.get(`${normName(pl.name)}|${pl.pos}`) ?? byName.get(normName(pl.name));
    return { ...pl, mean: proj?.mean ?? 0, low: proj?.low ?? 0, high: proj?.high ?? 0, projected: Boolean(proj) };
  });
}
