// After games are played (and nflverse updates), score each logged source and blend against actual points.
//   node scripts/blend-report.js
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { loadStats } from "../src/data/nflverse.js";
import { normName } from "../src/espn-roster.js";
import { joinActuals, blendReport } from "../src/projection-log.js";

if (!existsSync("logs")) { console.error("No logs/. Run scripts/log-projections.js weekly first."); process.exit(1); }
const logs = readdirSync("logs").filter((f) => f.endsWith(".json")).sort().map((f) => JSON.parse(readFileSync(`logs/${f}`, "utf8")));
const actuals = new Map(loadStats().map((r) => [`${r.season}|${r.week}|${normName(r.name)}|${r.pos}`, r.ppr]));
const weeks = joinActuals(logs, actuals);
if (!weeks.length) { console.error("No logged week has actual results yet."); process.exit(1); }
console.log(`${weeks.length} scored week(s)\nsource         n     MAE`);
for (const [s, v] of Object.entries(blendReport(weeks))) console.log(`${s.padEnd(13)} ${String(v.n).padStart(5)}  ${v.mae.toFixed(3)}`);
