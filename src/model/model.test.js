import { test } from "node:test";
import assert from "node:assert/strict";
import { blend, project, recentForm, shrink } from "./projection.js";
import { fitWeights, evaluate, walkForward } from "./backtest.js";

test("recentForm weights recent games more", () => {
  assert.ok(recentForm([5, 5, 20]) > 10);
  assert.equal(recentForm([8, 8, 8]), 8);
});

test("blend skips missing sources and honors weights", () => {
  assert.equal(blend({ a: 10, b: NaN, c: 20 }), 15);
  assert.equal(blend({ a: 10, c: 20 }, { a: 3, c: 1 }), 12.5);
});

test("shrink pulls small samples toward prior", () => {
  assert.ok(shrink(30, 10, 1) < 15);
  assert.ok(shrink(30, 10, 100) > 29);
});

test("injury and matchup adjust projection", () => {
  const base = project({ projections: { a: 20 } }).mean;
  assert.equal(project({ projections: { a: 20 }, injury: "Out" }).mean, 0);
  assert.ok(project({ projections: { a: 20 }, matchupFactor: 1.1 }).mean > base);
});

test("fitWeights favors the more accurate source", () => {
  const rows = [10, 12, 8, 15].map((actual) => ({ actual, projections: { good: actual + 1, bad: actual + 6 } }));
  const w = fitWeights(rows);
  assert.ok(w.good > w.bad);
  assert.ok(Math.abs(w.good + w.bad - 1) < 1e-9);
});

test("tuned weights beat equal weights in walk-forward backtest", () => {
  const wk = () => [10, 14, 7, 18, 12].map((actual) => ({ actual, projections: { good: actual + 1, bad: actual - 8 } }));
  const [r] = walkForward([wk(), wk()]);
  assert.ok(r.tuned.mae < r.equal.mae);
  assert.equal(evaluate([], {}).n, 0);
});
