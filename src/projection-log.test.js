import { test } from "node:test";
import assert from "node:assert/strict";
import { mergeSources, sleeperProjectionList, joinActuals, blendReport } from "./projection-log.js";

test("merge matches players across sources despite name formatting", () => {
  const rows = mergeSources({ model: [{ name: "A.J. Brown", pos: "WR", team: "PHI", mean: 14 }], sleeper: [{ name: "AJ Brown", pos: "WR", mean: 12 }] });
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].projections, { model: 14, sleeper: 12 });
});

test("sleeper list maps DEF to DST and skips unknown players", () => {
  const out = sleeperProjectionList({ 1: { pts_ppr: 9 }, 2: { pts_ppr: 5 }, 3: { pts_ppr: 1 } },
    { 1: { position: "DEF", team: "BUF" }, 2: { position: "WR", full_name: "X Y", team: "NE" } });
  assert.deepEqual(out.map((p) => [p.name, p.pos]), [["BUF D/ST", "DST"], ["X Y", "WR"]]);
});

test("blend report: tuned weights beat equal when one source is much better", () => {
  const mk = (actual) => ({ name: `p${actual}`, pos: "WR", actual, projections: { good: actual + 1, bad: actual + 9 } });
  const weeks = [1, 2, 3].map((w) => ({ season: 2026, week: w, rows: [10, 14, 7, 18].map(mk) }));
  const r = blendReport(weeks);
  assert.ok(r["tuned blend"].mae < r["equal blend"].mae);
  assert.ok(r.good.mae < r.bad.mae);
});

test("joinActuals drops unscored players", () => {
  const logs = [{ season: 2026, week: 1, rows: [{ name: "A B", pos: "WR", projections: {} }, { name: "C D", pos: "WR", projections: {} }] }];
  const out = joinActuals(logs, new Map([["2026|1|a b|WR", 11]]));
  assert.equal(out[0].rows.length, 1);
  assert.equal(out[0].rows[0].actual, 11);
});
