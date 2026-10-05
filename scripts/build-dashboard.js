// Builds dashboard/dist/index.html: template + this week's projections + league analysis + optimizer code.
//   node scripts/build-dashboard.js
// League source, in order: ESPN (ESPN_LEAGUE_ID, ESPN_TEAM_ID, [ESPN_S2, ESPN_SWID]), dashboard/league.json
// ({ teams: [{ id, name, mine?, roster: [{name,pos}] }], slots? }), else a simulated example league.
// A single-team dashboard/roster.json ({ team, roster, slots?, free? }) still drives the "My team" tab.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { getLeague, loadModelData } from "./lib-league.js";
import { projectWeek } from "./predict.js";
import { powerRankings, teamNeeds, findTrades } from "../src/trade.js";
import { leagueSpecs } from "../src/espn.js";

const ctx = loadModelData();
const { season, week } = ctx;
const proj = projectWeek({ ...ctx }).filter((p) => p.mean >= 0.5);
const acc = JSON.parse(readFileSync("dashboard/accuracy.json", "utf8"));
const r1 = (x) => +x.toFixed(1);
const wp = (p) => ({ n: p.name, p: p.pos, t: p.team, w: p.w.map(r1) });

// One entry per league, so the app can flip between them.
async function buildOne(spec, idx) {
  const { league, slots, meId, raw, weeks } = await getLeague(ctx, spec);
  const me = league.teams.find((t) => t.id === meId);
  // "My team" tab: the league's team when real, a roster.json when only that exists, else the example roster.
  let team;
  if (raw.example && existsSync("dashboard/roster.json")) {
    const f = JSON.parse(readFileSync("dashboard/roster.json", "utf8"));
    team = { name: f.team ?? "My team", roster: f.roster.map((p) => ({ n: p.name, p: p.pos })), slots: f.slots, free: f.free, example: false };
  } else {
    team = { name: me.name, roster: me.roster.map((p) => ({ n: p.name, p: p.pos })), slots: raw.example ? undefined : slots, free: league.freeAgents.map((p) => p.name), example: raw.example };
  }
  const t0 = Date.now();
  const needs = teamNeeds(league, meId, slots);
  const L = {
    example: raw.example, source: raw.source, weeks, slots, meId,
    power: powerRankings(league, slots).map((t) => ({ ...t, value: r1(t.value) })),
    needs: needs.needs.map((x) => ({ ...x, perWeek: r1(x.perWeek), solidGain: r1(x.solidGain), starGain: r1(x.starGain) })),
    chips: needs.chips.map((c) => ({ ...c, cost: r1(c.cost) })),
    ideas: findTrades(league, meId, slots, { top: 8 }).map((t) => ({ ...t, myDelta: r1(t.myDelta), theirDelta: r1(t.theirDelta), seasonPoints: r1(t.seasonPoints) })),
    teams: league.teams.map((t) => ({ id: t.id, name: t.name, mine: t.mine, roster: t.roster.map(wp) })),
  };
  const label = raw.example ? (spec ? `Example ${idx + 1}` : "Example league") : spec?.key && spec.key !== "LEAGUE" ? spec.key : raw.name ?? "My league";
  console.log(`${label}: ${raw.source}, ${league.teams.length} teams, ${((Date.now() - t0) / 1000).toFixed(0)}s analysis, ${L.ideas.length} trade ideas`);
  return { key: spec?.key ?? "DEFAULT", label, leagueName: raw.name, team, league: L };
}

const specs = leagueSpecs(process.env);
const leagues = [];
for (const [idx, spec] of (specs.length ? specs : [undefined]).entries()) {
  try { leagues.push(await buildOne(spec, idx)); } catch (e) { console.error(`League ${spec?.key} failed: ${e.message}`); if (specs.length < 2) throw e; }
}
if (!leagues.length) throw new Error("No league could be loaded");

const data = {
  season, week, leagues, ...acc,
  players: proj.map((p) => ({ n: p.name, p: p.pos, t: p.team, o: p.opp, s: p.spread, m: +p.mean.toFixed(2), l: +p.low.toFixed(1), h: +p.high.toFixed(1), q: p.injury })),
};
const inline = (f) => readFileSync(f, "utf8").replace(/^import .*$/gm, "").replace(/^export /gm, "");
const html = readFileSync("dashboard/template.html", "utf8")
  .replace("__DATA__", () => JSON.stringify(data)).replace("__LINEUP__", () => inline("src/lineup.js") + "\n" + inline("src/trade.js"));
mkdirSync("dashboard/dist", { recursive: true });
writeFileSync("dashboard/dist/index.html", html);
console.log(`dashboard/dist/index.html: ${data.players.length} players, ${leagues.length} league(s), ${(html.length / 1024).toFixed(0)} KB`);
