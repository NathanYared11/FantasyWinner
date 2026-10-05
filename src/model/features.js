// Builds leak-free features: everything for a game at index t uses only games before t.
import { POSITIONS } from "../data/nflverse.js";

export const FEATURES = [
  "ewma", "last", "mean16", "std16", "nCap", "gap", "ewmaUsage", "ewmaTargetShare", "ewmaAirShare",
  "implied", "spread", "home", "oppAllowed", "questionable", "doubtful",
];

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
const std = (a) => (a.length > 1 ? Math.sqrt(a.reduce((s, x) => s + (x - mean(a)) ** 2, 0) / (a.length - 1)) : 0);
function ewma(xs, halfLife) {
  let n = 0, d = 0;
  xs.forEach((x, i) => { const w = 0.5 ** ((xs.length - 1 - i) / halfLife); n += w * x; d += w; });
  return d ? n / d : 0;
}

export const LEAGUE_IMPLIED = 22.5;

// Index of points allowed by each defense to each position, per game-week.
export function buildDefenseIndex(stats) {
  const sums = new Map();
  for (const r of stats) {
    const k = `${r.opp}|${r.pos}|${r.idx}`;
    sums.set(k, (sums.get(k) ?? 0) + r.ppr);
  }
  const byKey = new Map();
  for (const [k, pts] of sums) {
    const [opp, pos, idx] = k.split("|");
    const kk = `${opp}|${pos}`;
    if (!byKey.has(kk)) byKey.set(kk, []);
    byKey.get(kk).push([Number(idx), pts]);
  }
  const posMean = {};
  for (const p of POSITIONS) posMean[p] = mean([...sums].filter(([k]) => k.split("|")[1] === p).map(([, v]) => v));
  for (const arr of byKey.values()) arr.sort((a, b) => a[0] - b[0]);
  return { byKey, posMean };
}

// Points per game a defense has recently allowed to a position, relative to league average.
export function oppAllowed(def, opp, pos, idx, window = 8) {
  const arr = def.byKey.get(`${opp}|${pos}`) ?? [];
  const prior = arr.filter(([i]) => i < idx).slice(-window).map(([, v]) => v);
  if (prior.length < 3) return 0;
  return mean(prior) - def.posMean[pos];
}

/**
 * history: this player's prior games, oldest first. ctx: { idx, opp, pos, game, injury, def }.
 * Returns an array aligned with FEATURES, or null when history is too short.
 */
export function featureVector(history, ctx) {
  if (history.length < 2) return null;
  const h = history.slice(-16);
  const pts = h.map((g) => g.ppr);
  const lastIdx = h[h.length - 1].idx;
  return [
    ewma(pts, 3), pts[pts.length - 1], mean(pts), std(pts), Math.min(h.length, 16) / 16,
    Math.min(ctx.idx - lastIdx - 1, 6),
    ewma(h.map((g) => g.usage), 3), ewma(h.map((g) => g.targetShare), 3), ewma(h.map((g) => g.airShare), 3),
    ctx.game?.implied ?? LEAGUE_IMPLIED, ctx.game?.spread ?? 0, ctx.game?.home ?? 0.5,
    oppAllowed(ctx.def, ctx.opp, ctx.pos, ctx.idx),
    ctx.injury === 1 ? 1 : 0, ctx.injury === 2 ? 1 : 0,
  ];
}

export function groupByPlayer(stats) {
  const m = new Map();
  for (const r of stats) {
    if (!m.has(r.id)) m.set(r.id, []);
    m.get(r.id).push(r);
  }
  return m;
}

// One training/eval row per played game: { pos, season, week, idx, x, y, id, name }.
export function buildRows(stats, games, injuries) {
  const def = buildDefenseIndex(stats);
  const rows = [];
  for (const hist of groupByPlayer(stats).values()) {
    hist.forEach((g, i) => {
      const x = featureVector(hist.slice(0, i), {
        idx: g.idx, opp: g.opp, pos: g.pos, def,
        game: games.get(`${g.season}|${g.week}|${g.team}`),
        injury: injuries.get(`${g.season}|${g.week}|${g.id}`) ?? 0,
      });
      if (x) rows.push({ id: g.id, name: g.name, pos: g.pos, season: g.season, week: g.week, idx: g.idx, x, y: g.ppr });
    });
  }
  return rows.sort((a, b) => a.idx - b.idx);
}
