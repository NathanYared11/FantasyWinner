// Weekly snapshots of every projection source, so blends can later be scored against actual results.
import { normName } from "./espn-roster.js";
import { fitWeights, mae } from "./model/backtest.js";
import { blend } from "./model/projection.js";

const key = (name, pos) => `${normName(name)}|${pos}`;

// sources: { model: [{name,pos,team,mean}], sleeper: [...], espn: [...] } -> one row per player.
export function mergeSources(sources) {
  const rows = new Map();
  for (const [src, list] of Object.entries(sources)) {
    for (const p of list) {
      const k = key(p.name, p.pos);
      if (!rows.has(k)) rows.set(k, { name: p.name, pos: p.pos, team: p.team, projections: {} });
      rows.get(k).projections[src] = p.mean;
    }
  }
  return [...rows.values()];
}

// Sleeper returns { [playerId]: { pts_ppr } } plus a players table for names.
export function sleeperProjectionList(projections, players, scoring = "pts_ppr") {
  const out = [];
  for (const [id, stats] of Object.entries(projections)) {
    const p = players[id];
    const pts = stats?.[scoring];
    if (!p || pts == null) continue;
    const pos = p.position === "DEF" ? "DST" : p.position;
    if (!["QB", "RB", "WR", "TE", "K", "DST"].includes(pos)) continue;
    out.push({ name: pos === "DST" ? `${p.team} D/ST` : p.full_name ?? `${p.first_name} ${p.last_name}`, pos, team: p.team, mean: pts });
  }
  return out;
}

// logs: [{ season, week, rows: [{name,pos,projections}] }]; actuals: Map "season|week|name|pos" -> points.
export function joinActuals(logs, actuals) {
  return logs.map((l) => ({
    ...l,
    rows: l.rows.map((r) => ({ ...r, actual: actuals.get(`${l.season}|${l.week}|${key(r.name, r.pos)}`) })).filter((r) => r.actual != null),
  })).filter((l) => l.rows.length);
}

// For each logged week, fit source weights on earlier weeks only, then score every approach.
export function blendReport(weeks) {
  const sources = [...new Set(weeks.flatMap((w) => w.rows.flatMap((r) => Object.keys(r.projections))))];
  const results = Object.fromEntries([...sources, "equal blend", "tuned blend"].map((s) => [s, []]));
  weeks.forEach((w, i) => {
    // Compare on players every source covers, so averages are apples to apples.
    const rows = w.rows.filter((r) => sources.every((s) => Number.isFinite(r.projections[s])));
    const weights = i > 0 ? fitWeights(weeks.slice(0, i).flatMap((x) => x.rows)) : null;
    for (const r of rows) {
      for (const s of sources) results[s].push([r.projections[s], r.actual]);
      results["equal blend"].push([blend(r.projections), r.actual]);
      if (weights) results["tuned blend"].push([blend(r.projections, weights), r.actual]);
    }
  });
  return Object.fromEntries(Object.entries(results).filter(([, v]) => v.length).map(([s, v]) => [s, { n: v.length, mae: mae(v) }]));
}
