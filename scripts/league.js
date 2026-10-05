// League report: power rankings, what your team needs, trade ideas, and a trade grader.
//   node scripts/league.js                         full report
//   node scripts/league.js grade --with 3 --give "Chris Olave" --get "Jahmyr Gibbs,Zay Flowers"
import { getLeague } from "./lib-league.js";
import { powerRankings, teamNeeds, findTrades, evaluateTrade } from "../src/trade.js";
import { pkey } from "../src/league.js";
import { normName } from "../src/espn-roster.js";

const args = process.argv.slice(2);
const opt = (k) => (args.includes(`--${k}`) ? args[args.indexOf(`--${k}`) + 1] : undefined);
const { league, slots, meId, raw, weeks } = await getLeague();
const nW = weeks.length, me = league.teams.find((t) => t.id === meId);
const f1 = (x) => (x >= 0 ? "+" : "") + x.toFixed(1);
if (raw.example) console.log("** EXAMPLE LEAGUE (simulated draft). Set ESPN_LEAGUE_ID/ESPN_TEAM_ID or add dashboard/league.json for yours. **\n");
console.log(`Rest of season: weeks ${weeks[0]}-${weeks.at(-1)}, your team: ${me.name}`);

if (args[0] === "grade") {
  const partner = league.teams.find((t) => String(t.id) === opt("with") || normName(t.name) === normName(opt("with") ?? ""));
  if (!partner) { console.error(`--with must be a team id or name: ${league.teams.map((t) => `${t.id}=${t.name}`).join(", ")}`); process.exit(2); }
  const find = (team, names) => names.split(",").map((n) => {
    const p = team.roster.find((x) => normName(x.name) === normName(n.trim()));
    if (!p) throw new Error(`${n.trim()} is not on ${team.name}`);
    return p;
  });
  const give = find(me, opt("give") ?? ""), get = find(partner, opt("get") ?? "");
  const r = evaluateTrade(me, partner, give, get, slots, nW);
  console.log(`\nGive ${give.map((p) => p.name).join(" + ")}  for  ${get.map((p) => p.name).join(" + ")}  (${partner.name})`);
  console.log(`Grade ${r.grade}: ${r.verdict}`);
  console.log(`You: ${f1(r.myDelta)} pts/week (${f1(r.seasonPoints)} over the rest of the season)`);
  console.log(`${partner.name}: ${f1(r.theirDelta)} pts/week. ${r.likelyAccepted ? "They should consider it." : "They are likely to decline."}`);
  if (r.dropped.length) console.log(`You would have to drop: ${r.dropped.join(", ")}`);
  try {
    const { FantasyCalcClient, marketDelta } = await import("../src/providers/fantasycalc.js");
    const md = marketDelta(await new FantasyCalcClient({ numTeams: league.teams.length }).values(), give.map((p) => p.name), get.map((p) => p.name));
    console.log(`Market (FantasyCalc trade values): ${md >= 0 ? "favors you" : "favors them"} by ${Math.abs(md).toFixed(0)}`);
  } catch (e) { console.log(`Market check skipped: ${e.message}`); }
  process.exit(0);
}

console.log("\nPower rankings (projected lineup points per week)");
powerRankings(league, slots).forEach((t, i) => console.log(`  ${String(i + 1).padStart(2)}. ${t.name.padEnd(22)} ${t.value.toFixed(1)}${t.mine ? "  <- you" : ""}`));

const n = teamNeeds(league, meId, slots);
console.log("\nWhat your team needs (rank among teams; points/week a solid starter or a star would add)");
for (const x of n.needs) console.log(`  ${x.pos.padEnd(3)} rank ${x.rank}/${x.of} (${x.grade})   solid ${f1(x.solidGain)}${x.solid ? ` (${x.solid})` : ""}   star ${f1(x.starGain)}${x.star ? ` (${x.star})` : ""}`);
if (n.chips.length) console.log("Trade chips (other teams would start them, you barely need them): " + n.chips.map((c) => `${c.name} (${c.pos}, wanted by ${c.wantedBy})`).join("; "));

console.log("\nTrade ideas where both teams improve");
const t0 = Date.now();
for (const t of findTrades(league, meId, slots)) console.log(`  [${t.grade}] with ${t.partner}: give ${t.give.join(" + ")} for ${t.get.join(" + ")}   you ${f1(t.myDelta)}/wk, them ${f1(t.theirDelta)}/wk`);
console.log(`(searched in ${((Date.now() - t0) / 1000).toFixed(1)}s)`);
