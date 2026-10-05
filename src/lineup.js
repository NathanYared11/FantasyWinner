// Exact lineup optimizer (DP over slots) + waiver-wire gain calculator.

export const SLOT_ELIGIBILITY = {
  QB: ["QB"], RB: ["RB"], WR: ["WR"], TE: ["TE"], K: ["K"], DST: ["DST"],
  FLEX: ["RB", "WR", "TE"], WRRB: ["RB", "WR"], SUPERFLEX: ["QB", "RB", "WR", "TE"],
};

export const DEFAULT_SLOTS = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 };

const expand = (slots) => Object.entries(slots).flatMap(([s, n]) => Array(n).fill(s));

/**
 * players: [{ name, pos, mean, low, high }]; slots: { QB: 1, FLEX: 1, ... }.
 * objective: "mean" (default), "floor" (safe) or "ceiling" (when you need a big week).
 * Returns { starters: [{slot, player}], bench: [...], total }.
 */
export function optimizeLineup(players, slots = DEFAULT_SLOTS, objective = "mean") {
  const key = objective === "floor" ? "low" : objective === "ceiling" ? "high" : "mean";
  const slotList = expand(slots);
  const n = slotList.length;
  const value = (p) => p[key] ?? p.mean ?? 0;
  // dp[mask] = best total + choice trail using the first i players; process players one at a time.
  let dp = new Map([[0, { total: 0, picks: [] }]]);
  players.forEach((p, pi) => {
    const next = new Map(dp);
    for (const [mask, state] of dp) {
      for (let s = 0; s < n; s++) {
        if (mask & (1 << s) || !SLOT_ELIGIBILITY[slotList[s]]?.includes(p.pos)) continue;
        const m2 = mask | (1 << s), total = state.total + value(p);
        if (!next.has(m2) || next.get(m2).total < total) next.set(m2, { total, picks: [...state.picks, [s, pi]] });
      }
    }
    dp = next;
  });
  // Prefer the best lineup that fills the most slots (some leagues leave slots unfillable).
  let best = null, bestCount = -1;
  for (const [mask, st] of dp) {
    const c = st.picks.length;
    if (c > bestCount || (c === bestCount && st.total > best.total)) { best = st; bestCount = c; }
  }
  const used = new Set(best.picks.map(([, pi]) => pi));
  return {
    starters: best.picks.sort((a, b) => a[0] - b[0]).map(([s, pi]) => ({ slot: slotList[s], player: players[pi] })),
    bench: players.filter((_, i) => !used.has(i)).sort((a, b) => value(b) - value(a)),
    total: best.total,
  };
}

// How many points does each free agent add to your best lineup (optionally dropping `drop`)?
export function waiverTargets(roster, freeAgents, slots = DEFAULT_SLOTS, { top = 10, objective = "mean" } = {}) {
  const base = optimizeLineup(roster, slots, objective).total;
  const out = [];
  for (const fa of freeAgents) {
    const gain = optimizeLineup([...roster, fa], slots, objective).total - base;
    if (gain > 0.05) out.push({ player: fa, gain });
  }
  return out.sort((a, b) => b.gain - a.gain).slice(0, top);
}

// Closest start/sit calls: bench players within `margin` points of the starter they'd replace.
export function closeCalls(result, margin = 2) {
  const calls = [];
  for (const b of result.bench) {
    for (const { slot, player } of result.starters) {
      if (SLOT_ELIGIBILITY[slot]?.includes(b.pos) && player.mean - b.mean <= margin) {
        calls.push({ slot, starter: player, bench: b, gap: player.mean - b.mean });
      }
    }
  }
  return calls.sort((a, b) => a.gap - b.gap);
}
