// Measure accuracy on past weeks and fit source weights from it.
// rows: [{ projections: {src: pts}, actual: pts, ...playerFields }]
import { blend, project, mean } from "./projection.js";

export const mae = (pairs) => mean(pairs.map(([p, a]) => Math.abs(p - a)));
export const rmse = (pairs) => Math.sqrt(mean(pairs.map(([p, a]) => (p - a) ** 2)));

// Weight each source by inverse MSE so the historically better source counts more.
export function fitWeights(rows) {
  const err = {};
  for (const r of rows) {
    for (const [src, p] of Object.entries(r.projections ?? {})) {
      if (Number.isFinite(p)) (err[src] ??= []).push((p - r.actual) ** 2);
    }
  }
  const inv = Object.fromEntries(Object.entries(err).map(([s, e]) => [s, 1 / (mean(e) + 1e-9)]));
  const total = Object.values(inv).reduce((a, b) => a + b, 0);
  return Object.fromEntries(Object.entries(inv).map(([s, v]) => [s, v / total]));
}

export function evaluate(rows, opts = {}) {
  const scored = rows.map((r) => ({ r, out: project(r, opts) })).filter((x) => Number.isFinite(x.out.mean));
  const pairs = scored.map(({ r, out }) => [out.mean, r.actual]);
  const covered = scored.filter(({ r, out }) => r.actual >= out.low && r.actual <= out.high).length;
  return { n: pairs.length, mae: mae(pairs), rmse: rmse(pairs), intervalCoverage: covered / (scored.length || 1) };
}

// Walk-forward: fit weights on earlier weeks, test on the next, so there is no lookahead.
// weeks: [rows, rows, ...] in chronological order.
export function walkForward(weeks, opts = {}) {
  const results = [];
  for (let i = 1; i < weeks.length; i++) {
    const weights = fitWeights(weeks.slice(0, i).flat());
    results.push({ week: i, tuned: evaluate(weeks[i], { ...opts, weights }), equal: evaluate(weeks[i], opts) });
  }
  return results;
}

export { blend };
