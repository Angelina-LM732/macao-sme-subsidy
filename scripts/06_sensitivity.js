// Sensitivity of headline results to each parameter that is a modelling choice.
const fs = require("fs");
const { simulate, allocation } = require("./sim.js");
const conn = JSON.parse(fs.readFileSync("out/connectedness.json"));
const cal = JSON.parse(fs.readFileSync("out/calibration.json"));
function rank(ps, k) { const s = ps.map((p, i) => [p[k], i]).sort((a, b) => b[0] - a[0]); const r = []; s.forEach(([, i], j) => r[i] = j + 1); return r; }
function headline(params = {}, extra = {}, mixOverride = null) {
  const c = mixOverride ? Object.assign({}, cal, { sectors: cal.sectors.map(s => s.key === "restaurant_local" ? Object.assign({}, s, { mix: mixOverride }) : s) }) : cal;
  const net = simulate(conn, c, Object.assign({ params }, extra));
  const firm = simulate(conn, c, Object.assign({ params, view: "firm" }, extra));
  const al = allocation(net.profiles, "jobsPerMOPm", 0.25);
  const rn = rank(net.profiles, "jobsPerMOPm"), rf = rank(firm.profiles, "jobsPerMOPm");
  let ov = 0; rn.forEach((r, i) => { if (r <= 20 && rf[i] <= 20) ov++; });
  return { ratio: al.ratio == null ? null : +al.ratio.toFixed(2), targeted: +al.targeted.toFixed(2), untargeted: +al.untargeted.toFixed(2), missed: 20 - ov,
           daly10: +(al.targeted * net.daly.total * 10).toFixed(2), dalyPerJob: +net.daly.total.toFixed(4) };
}
const rows = [];
const add = (group, label, h) => { rows.push(Object.assign({ group, label }, h)); console.log(group.padEnd(26), label.padEnd(22), JSON.stringify(h)); };
add("Baseline", "all defaults", headline());
for (const s of [0, 0.02, 0.03]) add("Bank spread over prime", "+" + s * 100 + "pp", headline({ loan_spread: s }));
for (const k of [6, 16]) add("Loan size (months)", k + " months", headline({ loan_months_of_fixed_cost: k }));
add("Loan repayment", "amortising over 36m", headline({ interest_only: false }));
add("Firm-level noise", "8%/month, persistence 0.5", headline({ idio_sd: 0.08, idio_rho: 0.5 }));
for (const v of [0.10, 0.40]) add("Neighbourhood visitor share", Math.round(v * 100) + "%", headline({}, {}, { visitor_fnb: v, supermarkets: 1 - v }));
for (const sh of [-15, -40]) add("Shock size", sh + "% visitors", headline({}, { shockPct: sh }));
add("Shock length", "2 quarters", headline({}, { duration: 2 }));
add("Retail exposure", "re-measured from 2025 visitor spending", headline({}, { exposureScale: cal.derived.exposure_scale_2025 }));
const B = cal.params.buffers;
add("Cash buffers", "half (US values / 2)", headline({ buffers: B.map(b => Math.round(b / 2)) }));
add("Cash buffers", "double (US values x 2)", headline({ buffers: B.map(b => b * 2) }));
add("Depression after job loss", "international, 18pp", headline({ excess_psych_prev: cal.params.excess_psych_prev_intl }));
add("Depression episode length", "mean 10.7 months", headline({ psych_duration_years: 10.7 / 12 }));
add("Excess mortality", "+63% (meta-analysis)", headline({ excess_mortality_rr: 0.63 }));
// rows where the comparison is undefined (no variation at all) are left out
fs.writeFileSync("out/sensitivity.json", JSON.stringify(rows.filter(r => r.ratio !== null), null, 1));
