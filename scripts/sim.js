// Stage 3b: monthly cash-flow Monte Carlo for SME profiles, with and without the
// 4% interest subsidy. Shared by the dashboard (browser) and the Node validation script,
// so the published numbers and the tested numbers come from the same code.
(function (root) {
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normals(n, seed) {
    const r = mulberry32(seed), out = new Float64Array(n);
    for (let i = 0; i < n; i += 2) {
      const u = Math.max(r(), 1e-12), v = r();
      const R = Math.sqrt(-2 * Math.log(u));
      out[i] = R * Math.cos(2 * Math.PI * v);
      if (i + 1 < n) out[i + 1] = R * Math.sin(2 * Math.PI * v);
    }
    return out;
  }

  function dalyPerJob(p) {
    const psych = p.excess_psych_prev * p.dw_depression * p.psych_duration_years;
    const mort = p.baseline_mortality * p.excess_mortality_rr * p.yll_per_death;
    return { psych, mort, total: psych + mort };
  }

  // Shock scenario (conditional forecast). The origin variable's LEVEL follows a set path:
  // `shockPct` below normal for `duration` quarters, then a straight-line recovery to normal
  // over `recovery` quarters. Because the VAR is in year-on-year log growth g, a level path L
  // implies g_h = L_h - L_{h-4}. Each quarter we solve the size of the origin shock s_h that
  // delivers the required g_h (given responses to earlier shocks, via the unit GIRFs), and
  // every other sector's growth follows the estimated network; its level path is then
  // rebuilt as L_h = g_h + L_{h-4}.
  function originLevel(o, H) {
    const T = Math.log(1 + o.shockPct / 100), path = [];
    for (let h = 0; h < H; h++) {
      if (h < o.duration) path.push(T);
      else { const k = h - o.duration + 1; path.push(o.recovery > 0 ? T * Math.max(0, 1 - k / o.recovery) : 0); }
    }
    return path;
  }
  function shockPath(conn, o) {
    const H = conn.horizon, N = conn.variables.length;
    const girf = conn.girf_unit[o.origin], io = conn.variables.indexOf(o.origin);
    const Lo = originLevel(o, H);
    const s = [], G = [], L = [];
    for (let h = 0; h < H; h++) {
      const gNeed = Lo[h] - (h >= 4 ? Lo[h - 4] : 0);
      let acc = 0; for (let k = 0; k < h; k++) acc += s[k] * girf[h - k][io];
      s.push((gNeed - acc) / girf[0][io]);
      const g = new Array(N).fill(0);
      for (let q = 0; q <= h; q++) for (let j = 0; j < N; j++) g[j] += s[q] * girf[h - q][j];
      G.push(g);
      L.push(g.map((x, j) => x + (h >= 4 ? L[h - 4][j] : 0)));
    }
    return L; // H x N, log level deviation from normal
  }

  // Sector log-revenue deviation per quarter for each noise path.
  // view "network": shock propagated through the estimated connectedness;
  // view "firm": firm-by-firm assessment of current conditions, no sector-wide shock.
  function sectorPaths(conn, sector, o, dev) {
    const vars = conn.variables, H = conn.horizon;
    const nP = Math.min(o.nPaths, conn.noise_paths.length);
    const out = new Float64Array(nP * H);
    for (let k = 0; k < nP; k++) {
      for (let h = 0; h < H; h++) {
        let d = 0;
        for (const v in sector.mix) {
          const j = vars.indexOf(v), w = sector.mix[v];
          const sc = (o.exposureScale && o.exposureScale[v] != null) ? o.exposureScale[v] : 1;
          const shock = o.view === "firm" ? 0 : dev[h][j] * sc;
          d += w * (shock + (o.noise ? conn.noise_paths[k][h][j] : 0));
        }
        out[k * H + h] = d;
      }
    }
    return { dev: out, nP };
  }

  function simulate(conn, cal, opt) {
    const P = Object.assign({}, cal.params, opt.params || {});
    const o = Object.assign({ shockPct: P.default_shock_pct, origin: P.default_origin, view: "network",
                              duration: P.default_duration_q, recovery: P.default_recovery_q,
                              nPaths: 600, noise: true, seed: 7 }, opt);
    const shock = shockPath(conn, o);
    const T = P.horizon_months, H = conn.horizon;
    const rate = P.prime_rate + P.loan_spread;
    const sr = Math.min(P.subsidy_rate, rate);
    const daly = dalyPerJob(P);
    const res = [];
    // common random numbers: identical idiosyncratic draws for every profile and both scenarios
    const nP = Math.min(o.nPaths, conn.noise_paths.length);
    const z = normals(nP * T, o.seed);
    for (const sec of cal.sectors) {
      const c = cal.cost[sec.cost];
      const { dev } = sectorPaths(conn, sec, o, shock);
      // margin profiles: sector margin -/0/+ one s.d. of its DSEC 2015-2024 annual margin
      const shifts = P.margin_sd ? [-P.margin_sd[sec.cost], 0, P.margin_sd[sec.cost]] : P.margin_shifts;
      for (const E of P.sizes) for (const B of P.buffers) for (const dm of shifts) {
        const R0 = c.rev_per_worker_month * E;
        const fixed = R0 * (c.wage_share + c.opex_share - dm);
        const L = Math.min(P.loan_cap, P.loan_months_of_fixed_cost * fixed);
        // credit lines are interest-only within the horizon; term loans amortise evenly
        const prin = P.interest_only ? 0 : L / P.subsidy_term_months;
        // cash buffer = B days of normal total outflows (goods + fixed costs), as in bank-account data
        const outflow = R0 * c.cogs_share + fixed;
        const cash00 = P.buffer_in_days ? B / 30.4 * outflow : B * fixed;
        let surv0 = 0, surv1 = 0, cost = 0;
        // optional: firms still open at the end of each month (display only; does not change any result)
        const tr0 = o.trace ? new Array(T).fill(0) : null, tr1 = o.trace ? new Array(T).fill(0) : null;
        for (let k = 0; k < nP; k++) {
          // proceeds_as_cash=false: the credit line is already drawn and spent (AMCM utilisation 84%),
          // so the firm starts with its cash buffer and carries the debt; the subsidy cuts its interest.
          let cash0 = cash00 + (P.proceeds_as_cash ? L : 0), cash1 = cash0, out0 = L, out1 = L, a0 = true, a1 = true, e = 0;
          for (let m = 0; m < T; m++) {
            e = P.idio_rho * e + P.idio_sd * z[k * T + m];
            const R = R0 * Math.exp(dev[k * H + Math.min(H - 1, Math.floor(m / 3))] + e);
            const op = R * (1 - c.cogs_share) - fixed;
            if (a0) { cash0 += op - out0 * rate / 12 - prin; out0 -= prin; if (cash0 < 0) a0 = false; }
            if (a1) {
              const g = out1 * sr / 12;           // government pays this share of interest
              cost += g;
              cash1 += op - out1 * (rate - sr) / 12 - prin; out1 -= prin; if (cash1 < 0) a1 = false;
            }
            if (tr0) { if (a0) tr0[m]++; if (a1) tr1[m]++; }
            if (!a0 && !a1) break;
          }
          if (a0) surv0++; if (a1) surv1++;
        }
        const p0 = surv0 / nP, p1 = surv1 / nP, d = p1 - p0, cst = cost / nP;
        const jobs = d * E;
        res.push({
          sector: sec.key, sectorName: sec.name, sectorZh: sec.zh, employees: E, buffer: B, bufferMonths: B,
          marginShift: dm, margin: c.margin + dm, loan: L, p0, p1, delta: d, expCost: cst,
          jobsSaved: jobs, jobsPerMOPm: cst > 0 ? jobs / (cst / 1e6) : 0,
          dalyAverted: jobs * daly.total, dalyPerMOPm: cst > 0 ? jobs * daly.total / (cst / 1e6) : 0,
          survPerMOPm: cst > 0 ? d / (cst / 1e6) : 0,
          ...(tr0 ? { alive0: tr0.map(v => v / nP), alive1: tr1.map(v => v / nP) } : {}),
        });
      }
    }
    return { profiles: res, rate, sr, daly, nPaths: nP, shock };
  }

  // Budget comparison: equal-weighted profile grid. 'Targeted' funds profiles in order of
  // jobs saved per MOP until `share` of the total budget is used.
  function allocation(profiles, key, share) {
    const tot = profiles.reduce((a, p) => a + p.expCost, 0);
    const totJobs = profiles.reduce((a, p) => a + p.jobsSaved, 0);
    const sorted = profiles.slice().sort((a, b) => b[key] - a[key]);
    let spent = 0, jobs = 0, n = 0;
    for (const p of sorted) { if (spent + p.expCost > tot * share) break; spent += p.expCost; jobs += p.jobsSaved; n++; }
    const untargeted = totJobs / tot * 1e6, targeted = spent > 0 ? jobs / spent * 1e6 : 0;
    return { untargeted, targeted, ratio: untargeted > 0 ? targeted / untargeted : null, nFunded: n };
  }

  const api = { simulate, allocation, dalyPerJob, shockPath };
  if (typeof module !== "undefined") module.exports = api; else root.SMESim = api;
})(this);
