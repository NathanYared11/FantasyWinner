// Project the next unplayed week. Usage: node scripts/predict.js [season] [week] [topN=15]
import { readFileSync } from "node:fs";
import { loadStats, loadGames, loadInjuries, POSITIONS } from "../src/data/nflverse.js";
import { buildDefenseIndex, featureVector, groupByPlayer, gameFor } from "../src/model/features.js";
import { predictRidge } from "../src/model/ridge.js";

const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
const models = JSON.parse(readFileSync("models/ridge.json", "utf8"));
const last = stats.at(-1);
const season = Number(process.argv[2]) || last.season;
const week = Number(process.argv[3]) || last.week + 1;
const topN = Number(process.argv[4]) || 15;
const def = buildDefenseIndex(stats);

export function projectWeek({ stats, games, injuries, models, season, week, def }) {
  const out = [];
  const idx = (season - 2000) * 18 + week;
  for (const hist of groupByPlayer(stats.filter((r) => r.idx < idx)).values()) {
    const lastGame = hist.at(-1);
    const game = games.get(`${season}|${week}|${lastGame.team}`);
    const env = gameFor({ ...lastGame, season, week }, games);
    if (!game || idx - lastGame.idx > 4) continue; // no game scheduled, or not recently active
    const injury = injuries.get(`${season}|${week}|${lastGame.id}`) ?? 0;
    if (injury === 3) continue; // ruled Out
    const x = featureVector(hist, { idx, opp: game.opp, pos: lastGame.pos, game: env, injury, def });
    const m = models.positions[lastGame.pos];
    if (!x || !m) continue;
    const mean = Math.max(0, predictRidge(m, x));
    out.push({ name: lastGame.name, pos: lastGame.pos, team: lastGame.team, opp: game.opp, spread: game.spread, total: game.total, home: game.home, mean, low: Math.max(0, mean - 1.28 * m.residualSd), high: mean + 1.28 * m.residualSd, injury });
  }
  return out.sort((a, b) => b.mean - a.mean);
}

if (process.argv[1].endsWith("predict.js")) {
  const proj = projectWeek({ stats, games, injuries, models, season, week, def });
  console.log(`Projections for ${season} week ${week} (PPR, ~80% range)`);
  for (const pos of POSITIONS) {
    console.log(`\n${pos}`);
    for (const p of proj.filter((r) => r.pos === pos).slice(0, topN)) {
      const tag = p.injury ? (p.injury === 1 ? " (Q)" : " (D)") : "";
      console.log(`  ${(p.name + tag).padEnd(26)} ${p.team} vs ${p.opp}  ${p.mean.toFixed(1).padStart(5)}  [${p.low.toFixed(0)}-${p.high.toFixed(0)}]`);
    }
  }
}
