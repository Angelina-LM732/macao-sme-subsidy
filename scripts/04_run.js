// Validation run of the simulation with default parameters; writes out/results_default.json
const fs = require("fs");
const { simulate, allocation, dalyPerJob } = require("./sim.js");
const conn = JSON.parse(fs.readFileSync("out/connectedness.json"));
const cal = JSON.parse(fs.readFileSync("out/calibration.json"));

function summary(r, label) {
  const ps = r.profiles;
  const bySec = {};
  for (const p of ps) {
    const s = (bySec[p.sectorName] ||= { n: 0, p0: 0, d: 0, jpm: 0, cost: 0, jobs: 0 });
    s.n++; s.p0 += p.p0; s.d += p.delta; s.cost += p.expCost; s.jobs += p.jobsSaved;
  }
  console.log(`\n== ${label}  rate=${(r.rate*100).toFixed(2)}% subsidy=${(r.sr*100).toFixed(2)}% paths=${r.nPaths}`);
  for (const [k, s] of Object.entries(bySec))
    console.log(k.padEnd(40), "surv0", (s.p0/s.n*100).toFixed(1).padStart(5), "| avg dSurv pp", (s.d/s.n*100).toFixed(2).padStart(5),
      "| jobs/MOPm", (s.jobs/(s.cost/1e6)).toFixed(2));
  const top = ps.slice().sort((a, b) => b.jobsPerMOPm - a.jobsPerMOPm).slice(0, 8);
  console.log("top profiles by jobs saved per MOP 1m:");
  for (const p of top) console.log(" ", p.sectorName.padEnd(38), "E", p.employees, "buf", p.bufferMonths, "m", (p.margin*100).toFixed(1),
    "p0", (p.p0*100).toFixed(1), "d", (p.delta*100).toFixed(1), "jobs/MOPm", p.jobsPerMOPm.toFixed(2));
  const maxd = ps.reduce((a, p) => Math.max(a, p.delta), 0);
  const nz = ps.filter(p => p.delta > 0.005).length;
  console.log("max delta pp", (maxd*100).toFixed(1), "profiles with delta>0.5pp:", nz, "/", ps.length);
  console.log("allocation 25%:", allocation(ps, "jobsPerMOPm", 0.25));
}

const t0 = Date.now();
const net = simulate(conn, cal, {});
console.log("runtime ms", Date.now() - t0, "DALY/job", dalyPerJob(cal.params));
summary(net, "NETWORK view, visitors -25%");
const iso = simulate(conn, cal, { view: "firm" });
summary(iso, "FIRM-BY-FIRM view (no sector shock)");
console.log("shock path (visitors, fnb, jewellery, souvenir, supermarkets):", net.shock.map(r=>[0,3,4,7,8].map(j=>r[j].toFixed(2)).join(" ")));
const l3 = simulate(conn, cal, { params: { loan_months_of_fixed_cost: 3 } });
summary(l3, "NETWORK, loan = 3 months");

// rank agreement between isolated and network views (Spearman on jobs per MOP)
function ranks(a) { const idx = a.map((v, i) => [v, i]).sort((x, y) => y[0] - x[0]); const r = []; idx.forEach(([, i], k) => r[i] = k); return r; }
const rn = ranks(net.profiles.map(p => p.jobsPerMOPm)), ri = ranks(iso.profiles.map(p => p.jobsPerMOPm));
const n = rn.length; const d2 = rn.reduce((a, r, i) => a + (r - ri[i]) ** 2, 0);
console.log("\nSpearman(network, isolated) =", (1 - 6 * d2 / (n * (n * n - 1))).toFixed(3));
const topN = new Set(rn.map((r, i) => r < 20 ? i : -1).filter(i => i >= 0));
const topI = new Set(ri.map((r, i) => r < 20 ? i : -1).filter(i => i >= 0));
console.log("top-20 overlap:", [...topN].filter(i => topI.has(i)).length);
fs.writeFileSync("out/results_default.json", JSON.stringify({ network: net, isolated: iso }));
