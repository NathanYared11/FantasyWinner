// Snapshot this week's projections from our model + Sleeper (+ optional ESPN) into logs/.
// Run it BEFORE games each week:  node scripts/log-projections.js [season] [week]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { loadStats, loadGames, loadInjuries } from "../src/data/nflverse.js";
import { buildDefenseIndex } from "../src/model/features.js";
import { projectWeek } from "./predict.js";
import { SleeperClient } from "../src/providers/sleeper.js";
import { mergeSources, sleeperProjectionList } from "../src/projection-log.js";

const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
const models = JSON.parse(readFileSync("models/ridge.json", "utf8"));
const season = Number(process.argv[2]) || stats.at(-1).season;
const week = Number(process.argv[3]) || stats.at(-1).week + 1;

const sources = { model: projectWeek({ stats, games, injuries, models, season, week, def: buildDefenseIndex(stats) }) };
try {
  const sleeper = new SleeperClient();
  const [proj, players] = await Promise.all([sleeper.projections(season, week), sleeper.players()]);
  sources.sleeper = sleeperProjectionList(proj, players);
} catch (e) {
  console.error(`Sleeper skipped: ${e.message}`);
}
mkdirSync("logs", { recursive: true });
const rows = mergeSources(sources);
writeFileSync(`logs/${season}_w${String(week).padStart(2, "0")}.json`, JSON.stringify({ season, week, sources: Object.keys(sources), rows }));
console.log(`logged ${rows.length} players for ${season} week ${week} from ${Object.keys(sources).join(", ")}`);
