// Blends several projection sources and adjusts for form, injury, and matchup.
// Every input is optional; missing signals are skipped, not guessed.

export const INJURY_MULTIPLIER = { Out: 0, IR: 0, Doubtful: 0.25, Questionable: 0.9, Probable: 0.98 };

export const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);

export function stdev(xs) {
  if (xs.length < 2) return NaN;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
}

// Exponentially weighted average, most recent game last. halfLife is in games.
export function recentForm(scores, halfLife = 3) {
  if (!scores.length) return NaN;
  let num = 0, den = 0;
  scores.forEach((s, i) => {
    const w = 0.5 ** ((scores.length - 1 - i) / halfLife);
    num += w * s;
    den += w;
  });
  return num / den;
}

// Weighted average of source projections. weights: { sourceName: w } (default equal).
export function blend(projections, weights = {}) {
  let num = 0, den = 0;
  for (const [src, p] of Object.entries(projections)) {
    if (!Number.isFinite(p)) continue;
    const w = weights[src] ?? 1;
    num += w * p;
    den += w;
  }
  return den ? num / den : NaN;
}

// Pull a noisy estimate toward the position mean; fewer games => more shrinkage.
export function shrink(estimate, prior, games, k = 4) {
  return (games * estimate + k * prior) / (games + k);
}

/**
 * player: { projections: {src: pts}, history: [pts...], injury, matchupFactor, positionMean }
 * Returns { mean, low, high } where low/high is an ~80% interval.
 */
export function project(player, { weights, formWeight = 0.3 } = {}) {
  const history = player.history ?? [];
  const sources = blend(player.projections ?? {}, weights);
  const form = history.length ? shrink(recentForm(history), player.positionMean ?? mean(history), history.length) : NaN;

  let base;
  if (Number.isFinite(sources) && Number.isFinite(form)) base = (1 - formWeight) * sources + formWeight * form;
  else base = Number.isFinite(sources) ? sources : form;
  if (!Number.isFinite(base)) return { mean: NaN, low: NaN, high: NaN };

  const injury = INJURY_MULTIPLIER[player.injury] ?? 1;
  const matchup = player.matchupFactor ?? 1; // e.g. 1.1 vs a weak defense
  const m = base * injury * matchup;

  const sd = stdev(history);
  const spread = (Number.isFinite(sd) ? sd : 0.35 * m) * 1.28 * injury;
  return { mean: m, low: Math.max(0, m - spread), high: m + spread };
}
