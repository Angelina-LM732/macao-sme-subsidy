// Validation: normal-times (no shock, no subsidy) 24-month failure across profiles vs AMCM
// SME loan delinquency ratio. Writes the figure into calibration.json's source note.
const fs = require("fs");
const { simulate } = require("./sim.js");
const conn = JSON.parse(fs.readFileSync("out/connectedness.json"));
const cal = JSON.parse(fs.readFileSync("out/calibration.json"));
const r = simulate(conn, cal, { view: "firm" });
const f = 1 - r.profiles.reduce((a, p) => a + p.p0, 0) / r.profiles.length;
cal.derived.validation_failure = +f.toFixed(4);
for (const s of cal.sources) s.basis = s.basis.replace("VALIDATION_FAILURE", (f * 100).toFixed(1) + "%");
fs.writeFileSync("out/calibration.json", JSON.stringify(cal, null, 1));
console.log("normal-times 24-month failure:", (f * 100).toFixed(1) + "%", "vs AMCM delinquency", cal.params.validation_delinquency * 100 + "%");
