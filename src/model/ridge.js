// Ridge regression via normal equations (features standardized, intercept unpenalized).
function solve(A, b) {
  const n = b.length;
  const M = A.map((row, i) => [...row, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / M[c][c];
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / M[r][r];
  }
  return x;
}

export function fitRidge(X, y, lambda = 10) {
  const n = X.length, d = X[0].length;
  const mean = new Array(d).fill(0), std = new Array(d).fill(0);
  for (const r of X) r.forEach((v, j) => (mean[j] += v / n));
  for (const r of X) r.forEach((v, j) => (std[j] += (v - mean[j]) ** 2 / n));
  std.forEach((v, j) => (std[j] = Math.sqrt(v) || 1));
  const yMean = y.reduce((a, b) => a + b, 0) / n;
  const A = Array.from({ length: d }, () => new Array(d).fill(0));
  const b = new Array(d).fill(0);
  for (let i = 0; i < n; i++) {
    const z = X[i].map((v, j) => (v - mean[j]) / std[j]);
    for (let j = 0; j < d; j++) {
      b[j] += z[j] * (y[i] - yMean);
      for (let k = j; k < d; k++) A[j][k] += z[j] * z[k];
    }
  }
  for (let j = 0; j < d; j++) {
    for (let k = 0; k < j; k++) A[j][k] = A[k][j];
    A[j][j] += lambda;
  }
  return { weights: solve(A, b), mean, std, intercept: yMean, lambda };
}

export function predictRidge(model, x) {
  return x.reduce((s, v, j) => s + model.weights[j] * ((v - model.mean[j]) / model.std[j]), model.intercept);
}
