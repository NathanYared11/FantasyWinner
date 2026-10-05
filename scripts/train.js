// Walk-forward evaluation + final model fit. Usage: node scripts/train.js [testFromSeason=2024]
import { writeFileSync, mkdirSync } from "node:fs";
import { loadStats, loadGames, loadInjuries, POSITIONS } from "../src/data/nflverse.js";
import { buildRows, FEATURES } from "../src/model/features.js";
import { fitRidge, predictRidge } from "../src/model/ridge.js";

const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
if (!stats.length) { console.error("No data. Run scripts/fetch-data.sh first."); process.exit(1); }
const rows = buildRows(stats, games, injuries);
console.log(`${stats.length} player-games, ${rows.length} feature rows, seasons ${stats[0].season}-${stats.at(-1).season}`);

const F = Object.fromEntries(FEATURES.map((f, i) => [f, i]));
const relevant = (r) => r.x[F.ewma] >= 6; // fantasy-relevant players

// Walk-forward: for every week in [fromSeason, end], fit on all earlier rows, predict that week.
function walkForward(fromSeason, toSeason, lambda) {
  const preds = [];
  const weeks = [...new Set(rows.filter((r) => r.season >= fromSeason && r.season <= toSeason).map((r) => r.idx))];
  for (const idx of weeks) {
    for (const pos of POSITIONS) {
      const train = rows.filter((r) => r.pos === pos && r.idx < idx);
      const test = rows.filter((r) => r.pos === pos && r.idx === idx);
      if (train.length < 200 || !test.length) continue;
      const m = fitRidge(train.map((r) => r.x), train.map((r) => r.y), lambda);
      for (const r of test) preds.push({ ...r, ridge: Math.max(0, predictRidge(m, r.x)), ewma: r.x[F.ewma], mean16: r.x[F.mean16] });
    }
  }
  return preds;
}

const mae = (p, k) => p.reduce((s, r) => s + Math.abs(r[k] - r.y), 0) / p.length;
const rmse = (p, k) => Math.sqrt(p.reduce((s, r) => s + (r[k] - r.y) ** 2, 0) / p.length);

function rank(a) {
  const o = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]);
  const r = new Array(a.length);
  o.forEach(([, i], k) => (r[i] = k));
  return r;
}
function spearman(a, b) {
  const ra = rank(a), rb = rank(b), n = a.length, ma = (n - 1) / 2;
  let c = 0, va = 0, vb = 0;
  for (let i = 0; i < n; i++) { c += (ra[i] - ma) * (rb[i] - ma); va += (ra[i] - ma) ** 2; vb += (rb[i] - ma) ** 2; }
  return c / Math.sqrt(va * vb);
}
// Mean per-week rank correlation between projected and actual points (what start/sit cares about).
function weeklySpearman(p, k) {
  const byWeek = new Map();
  for (const r of p) (byWeek.get(r.idx) ?? byWeek.set(r.idx, []).get(r.idx)).push(r);
  const cs = [...byWeek.values()].filter((w) => w.length >= 20).map((w) => spearman(w.map((r) => r[k]), w.map((r) => r.y)));
  return cs.reduce((a, b) => a + b, 0) / cs.length;
}

function report(title, p) {
  console.log(`\n${title} (n=${p.length})`);
  console.log("model     MAE    RMSE   weekly-rank-corr");
  for (const k of ["mean16", "ewma", "ridge"]) {
    console.log(`${k.padEnd(8)} ${mae(p, k).toFixed(3)}  ${rmse(p, k).toFixed(3)}  ${weeklySpearman(p, k).toFixed(3)}`);
  }
}

// 1) Tune lambda on 2023 only (never touches the test seasons).
const testFrom = Number(process.argv[2]) || 2024;
const lastSeason = stats.at(-1).season;
let best = { lambda: 10, err: Infinity };
for (const lambda of [1, 10, 100, 1000]) {
  const e = rmse(walkForward(testFrom - 1, testFrom - 1, lambda).filter(relevant), "ridge");
  console.log(`tune lambda=${lambda}: RMSE ${e.toFixed(3)} on ${testFrom - 1}`);
  if (e < best.err) best = { lambda, err: e };
}

// 2) Out-of-sample evaluation.
const preds = walkForward(testFrom, lastSeason, best.lambda);
report(`ALL players, ${testFrom}-${lastSeason}`, preds);
report(`Fantasy-relevant (ewma >= 6), ${testFrom}-${lastSeason}`, preds.filter(relevant));
for (const pos of POSITIONS) report(`${pos} (relevant)`, preds.filter((r) => r.pos === pos && relevant(r)));

// 3) Final per-position models on all history.
const models = { features: FEATURES, lambda: best.lambda, trainedThrough: lastSeason, positions: {} };
for (const pos of POSITIONS) {
  const t = rows.filter((r) => r.pos === pos);
  const m = fitRidge(t.map((r) => r.x), t.map((r) => r.y), best.lambda);
  models.positions[pos] = { ...m, n: t.length, residualSd: Math.sqrt(t.reduce((s, r) => s + (predictRidge(m, r.x) - r.y) ** 2, 0) / t.length) };
  const top = FEATURES.map((f, j) => [f, m.weights[j]]).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 4);
  console.log(`${pos} top drivers: ${top.map(([f, w]) => `${f} ${w > 0 ? "+" : ""}${w.toFixed(2)}`).join(", ")}`);
}
mkdirSync("models", { recursive: true });
writeFileSync("models/ridge.json", JSON.stringify(models));
console.log("saved models/ridge.json");
