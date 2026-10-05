// Trade grading, team needs and trade finding, all based on how each team's best lineup changes
// over the rest of the season (byes, injuries-to-date and matchups are baked into weekly projections).
import { optimizeLineup } from "./lineup.js";

export const DEPTH_CREDIT = 0.1; // a bench player is worth ~10% of his points: roughly how often a starter misses a week

const total = (a) => a.reduce((x, y) => x + y, 0);
const POS = ["QB", "RB", "WR", "TE", "K", "DST"];

// Expected lineup points per week over the remaining weeks, plus a small credit for bench depth.
export function rosValue(roster, slots, nWeeks) {
  let t = 0;
  for (let i = 0; i < nWeeks; i++) {
    const wk = roster.map((p) => ({ name: p.name, pos: p.pos, mean: p.w[i] ?? 0 }));
    const res = optimizeLineup(wk, slots);
    t += res.total + DEPTH_CREDIT * total(res.bench.slice(0, 3).map((p) => p.mean));
  }
  return t / nWeeks;
}

// If a team ends up with more players than before, it drops its least valuable ones.
function settle(roster, size) {
  const r = [...roster];
  while (r.length > size) {
    let worst = 0;
    r.forEach((p, i) => { if (total(p.w) < total(r[worst].w)) worst = i; });
    r.splice(worst, 1);
  }
  return r;
}

const letter = (d) => (d >= 2.5 ? "A+" : d >= 1.5 ? "A" : d >= 0.8 ? "B+" : d >= 0.3 ? "B" : d >= -0.1 ? "C" : d >= -0.6 ? "D" : "F");

/** give/get: arrays of player objects. Returns per-week deltas for both sides and a verdict. */
export function evaluateTrade(me, partner, give, get, slots, nWeeks) {
  const gone = new Set(give), taken = new Set(get);
  const myAfter = settle([...me.roster.filter((p) => !gone.has(p)), ...get], me.roster.length);
  const theirAfter = settle([...partner.roster.filter((p) => !taken.has(p)), ...give], partner.roster.length);
  const myDelta = rosValue(myAfter, slots, nWeeks) - rosValue(me.roster, slots, nWeeks);
  const theirDelta = rosValue(theirAfter, slots, nWeeks) - rosValue(partner.roster, slots, nWeeks);
  const grade = letter(myDelta);
  const verdict = myDelta >= 0.3 && theirDelta >= -0.1 ? "Win-win: both teams improve"
    : myDelta >= 0.3 ? "You win; they may see it as a loss"
    : myDelta < -0.1 && theirDelta >= 0.3 ? "They win. Pass or ask for more"
    : myDelta < -0.1 ? "Both teams get worse"
    : "About even";
  return {
    myDelta, theirDelta, grade, verdict,
    seasonPoints: myDelta * nWeeks, // rough total over the remaining weeks
    likelyAccepted: theirDelta >= -0.1,
    dropped: me.roster.filter((p) => !gone.has(p) && !myAfter.includes(p)).map((p) => p.name),
  };
}

const rankLetter = (rank, n) => { const f = (rank - 1) / Math.max(1, n - 1); return f <= 0.15 ? "A" : f <= 0.4 ? "B" : f <= 0.65 ? "C" : f <= 0.85 ? "D" : "F"; };

// Average weekly points from the top-k players at a position, per team, ranked across the league.
export function positionStrength(teams, slots, nWeeks) {
  const out = {};
  for (const pos of POS) {
    const k = Math.max(1, slots[pos] ?? 0);
    const rows = teams.map((t) => {
      const ps = t.roster.filter((p) => p.pos === pos);
      let s = 0;
      for (let i = 0; i < nWeeks; i++) s += total(ps.map((p) => p.w[i] ?? 0).sort((a, b) => b - a).slice(0, k));
      return { id: t.id, value: s / nWeeks };
    }).sort((a, b) => b.value - a.value);
    out[pos] = rows.map((r, i) => ({ ...r, rank: i + 1, grade: rankLetter(i + 1, rows.length) }));
  }
  return out;
}

/** What the team needs: per-position rank and the points/week a solid or star addition would add. */
export function teamNeeds(league, meId, slots) {
  const nW = league.weeks.length, teams = league.teams, me = teams.find((t) => t.id === meId);
  const strength = positionStrength(teams, slots, nW);
  const base = rosValue(me.roster, slots, nW);
  const universe = [...teams.filter((t) => t.id !== meId).flatMap((t) => t.roster), ...league.freeAgents];
  const needs = POS.map((pos) => {
    const row = strength[pos].find((r) => r.id === meId);
    const ranked = universe.filter((p) => p.pos === pos).sort((a, b) => total(b.w) - total(a.w));
    const solid = ranked[Math.min(teams.length, ranked.length) - 1], star = ranked[Math.max(0, Math.floor(teams.length / 3) - 1)];
    const gain = (p) => (p ? rosValue([...me.roster, p], slots, nW) - base : 0);
    return { pos, rank: row.rank, of: teams.length, grade: row.grade, perWeek: row.value, solidGain: gain(solid), starGain: gain(star), solid: solid?.name, star: star?.name };
  });
  // Trade chips: players who would start for other teams but barely matter to you.
  const chips = me.roster.map((p) => {
    const mine = rosValue(me.roster.filter((x) => x !== p), slots, nW);
    const cost = base - mine;
    const wantedBy = teams.filter((t) => t.id !== meId && rosValue([...t.roster, p], slots, nW) - rosValue(t.roster, slots, nW) >= 0.4).length;
    return { name: p.name, pos: p.pos, cost, wantedBy };
  }).filter((c) => c.cost < 0.6 && c.wantedBy > 0).sort((a, b) => b.wantedBy - a.wantedBy).slice(0, 5);
  return { needs: needs.sort((a, b) => b.solidGain - a.solidGain), chips, strength, base };
}

export function powerRankings(league, slots) {
  const nW = league.weeks.length;
  return league.teams.map((t) => ({ id: t.id, name: t.name, mine: t.mine, value: rosValue(t.roster, slots, nW) })).sort((a, b) => b.value - a.value);
}

/** Search 1-for-1 and 2-for-1 deals where I gain, ranked by my gain with partner's gain shown. */
export function findTrades(league, meId, slots, { top = 8, minGain = 0.3 } = {}) {
  const nW = league.weeks.length, me = league.teams.find((t) => t.id === meId);
  const base = rosValue(me.roster, slots, nW);
  const found = [];
  for (const partner of league.teams.filter((t) => t.id !== meId)) {
    const targets = partner.roster
      .map((t) => ({ t, add: rosValue([...me.roster, t], slots, nW) - base }))
      .filter((x) => x.add >= minGain + 0.2).sort((a, b) => b.add - a.add).slice(0, 4);
    for (const { t } of targets) {
      const mine = me.roster.filter((p) => total(p.w) > 0);
      const options = mine.map((g) => [g]);
      const low = [...mine].sort((a, b) => total(a.w) - total(b.w)).slice(0, 6);
      for (let i = 0; i < low.length; i++) for (let j = i + 1; j < low.length; j++) options.push([low[i], low[j]]);
      for (const give of options) {
        const r = evaluateTrade(me, partner, give, [t], slots, nW);
        if (r.myDelta >= minGain && r.theirDelta >= 0) found.push({ partner: partner.name, partnerId: partner.id, give: give.map((p) => p.name), get: [t.name], ...r });
      }
    }
  }
  // Only deals where the other side also gains are returned, ranked by my gain.
  return found.sort((a, b) => b.myDelta - a.myDelta).slice(0, top);
}
