// Builds dashboard/dist/index.html: the template + this week's projections + the optimizer code.
//   node scripts/build-dashboard.js [season] [week]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { loadStats, loadGames, loadInjuries } from "../src/data/nflverse.js";
import { buildDefenseIndex } from "../src/model/features.js";
import { projectWeek } from "./predict.js";

const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
const models = JSON.parse(readFileSync("models/ridge.json", "utf8"));
const season = Number(process.argv[2]) || stats.at(-1).season;
const week = Number(process.argv[3]) || stats.at(-1).week + 1;
const proj = projectWeek({ stats, games, injuries, models, season, week, def: buildDefenseIndex(stats) }).filter((p) => p.mean >= 0.5);

// Walk-forward accuracy numbers come from scripts/train.js output (relevant players, 2024+).
const acc = JSON.parse(readFileSync("dashboard/accuracy.json", "utf8"));
const sample = ["Josh Allen QB", "Bijan Robinson RB", "Jonathan Taylor RB", "Kyren Williams RB", "Puka Nacua WR", "Chris Olave WR", "Zay Flowers WR", "Trey McBride TE", "Brandon Aubrey K", "CIN D/ST DST"]
  .map((s) => ({ n: s.slice(0, s.lastIndexOf(" ")), p: s.slice(s.lastIndexOf(" ") + 1) }));
const data = {
  season, week, sample, ...acc,
  players: proj.map((p) => ({ n: p.name, p: p.pos, t: p.team, o: p.opp, m: +p.mean.toFixed(2), l: +p.low.toFixed(1), h: +p.high.toFixed(1), q: p.injury })),
};
const lineup = readFileSync("src/lineup.js", "utf8").replace(/^export /gm, "");
const html = readFileSync("dashboard/template.html", "utf8").replace("__DATA__", () => JSON.stringify(data)).replace("__LINEUP__", () => lineup);
mkdirSync("dashboard/dist", { recursive: true });
writeFileSync("dashboard/dist/index.html", html);
console.log(`dashboard/dist/index.html: ${data.players.length} players, ${(html.length / 1024).toFixed(0)} KB`);
