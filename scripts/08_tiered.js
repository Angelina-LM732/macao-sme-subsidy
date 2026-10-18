// Tiered subsidy design at equal cost.
// The scheme is not budget-constrained (about MOP 4.5bn of the MOP 10bn loan cap used by
// 31 Mar 2026), so the policy question is not "who to ration" but "what rate to offer whom".
// For every profile we simulate survival and subsidy cost at a menu of subsidy rates, then
// compare a flat 4% with two-tier designs that cost no more in total.
const fs = require("fs");
const { simulate } = require("./sim.js");
const conn = JSON.parse(fs.readFileSync("out/connectedness.json"));
const cal = JSON.parse(fs.readFileSync("out/calibration.json"));

const bank = cal.params.prime_rate + cal.params.loan_spread;          // 6.25%
const menu = [0, 0.01, 0.02, 0.03, 0.04, 0.05, bank];
const runs = menu.map(r => simulate(conn, cal, { params: { subsidy_rate: r } }).profiles);
const nP = runs[0].length;
// jobs saved relative to no subsidy, expected subsidy cost, at each menu rate
const jobs = (k, i) => (runs[k][i].p1 - runs[0][i].p0) * runs[k][i].employees;
const cost = (k, i) => runs[k][i].expCost;
const K4 = menu.indexOf(0.04);

let flatJobs = 0, flatCost = 0;
for (let i = 0; i < nP; i++) { flatJobs += jobs(K4, i); flatCost += cost(K4, i); }

// priority order = jobs per MOP at the flat 4% (the dashboard ranking)
const order = [...Array(nP).keys()].sort((a, b) => runs[K4][b].jobsPerMOPm - runs[K4][a].jobsPerMOPm);
let best = null; const designs = [];
for (const share of [0.1, 0.2, 0.25, 0.3, 0.4, 0.5]) {
  const top = new Set(order.slice(0, Math.round(share * nP)));
  for (let kh = K4; kh < menu.length; kh++) for (let kl = 0; kl <= K4; kl++) {
    let J = 0, C = 0;
    for (let i = 0; i < nP; i++) { const k = top.has(i) ? kh : kl; J += jobs(k, i); C += cost(k, i); }
    if (C <= flatCost * 1.0001) {
      const d = { topShare: share, highRate: menu[kh], lowRate: menu[kl], jobs: J, cost: C, gain: J / flatJobs - 1 };
      designs.push(d); if (!best || J > best.jobs) best = d;
    }
  }
}
// best design per top share, for the table
const byShare = {};
for (const d of designs) if (!byShare[d.topShare] || d.jobs > byShare[d.topShare].jobs) byShare[d.topShare] = d;

const out = {
  bank_rate: bank, flat: { rate: 0.04, jobs: +flatJobs.toFixed(2), cost: Math.round(flatCost) },
  best: { ...best, jobs: +best.jobs.toFixed(2), cost: Math.round(best.cost), gain: +best.gain.toFixed(4) },
  by_share: Object.values(byShare).map(d => ({ topShare: d.topShare, highRate: d.highRate, lowRate: d.lowRate, gain: +d.gain.toFixed(4), costVsFlat: +(d.cost / flatCost).toFixed(3) })),
  note: "Equal-weighted profile grid; jobs saved relative to no subsidy; cost = expected subsidy outlay over 24 months.",
  uptake: { loans_mop: 4.5e9, cap_mop: 1e10, as_of: "2026-03-31", deadline: "2026-12-31",
            source: "https://www.gov.mo/zh-hant/news/1225389/" },
};
fs.writeFileSync("out/tiered.json", JSON.stringify(out, null, 1));
console.log("flat 4%: jobs", flatJobs.toFixed(2), "cost", Math.round(flatCost));
console.log("best:", out.best);
console.table(out.by_share);
