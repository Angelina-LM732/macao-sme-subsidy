"""Validation of the propagation model on Macao's own history.

A. COVID back-test: estimate the VAR on 2011Q1-2019Q4 only, feed in the ACTUAL visitor path
   of 2020Q1-2022Q4, let every other sector follow the estimated network, and compare with
   what actually happened (log level relative to the same quarter of 2019).
C. Recent out-of-sample test: estimate on 2011Q1-2024Q4 (main specification), feed in actual
   visitor growth for 2025Q1-2026Q2, and compare sector growth with outcomes.
D. Structural change: with visitor numbers back near 2019, how much does each sector sell
   compared with 2019? Plus DSEC tourism ratios 2019 vs 2024.

Conditional forecast: each quarter, the shock to the origin variable is chosen so that the
origin matches its actual value; the shock enters all sectors through the estimated
covariance (generalised impulse), exactly as in the dashboard.
Output: out/backtest.json
"""
import numpy as np, pandas as pd, json

g_all = pd.read_csv("data/panel_growth.csv", index_col=0)
lv = pd.read_csv("data/panel_levels.csv", index_col=0)
names = list(g_all.columns); N = len(names); O = names.index("visitors")
others = [n for n in names if n != "visitors"]
WINSOR = 1.0


def fit_var1(Y):
    X = np.hstack([np.ones((len(Y) - 1, 1)), Y[:-1]])
    B, *_ = np.linalg.lstsq(X, Y[1:], rcond=None)
    U = Y[1:] - X @ B
    S = U.T @ U / (len(U) - X.shape[1])
    return B[0], B[1:].T, S          # const, Phi, Sigma


def cond_forecast(c, Phi, S, z0, origin_path, o=O):
    """z0: last observed state. origin_path: actual values of the origin variable."""
    z, out = z0.copy(), []
    for x in origin_path:
        zp = c + Phi @ z
        s = x - zp[o]
        z = zp + S[:, o] / S[o, o] * s
        out.append(z.copy())
    return np.array(out)


def spearman(a, b):
    ra, rb = pd.Series(a).rank().values, pd.Series(b).rank().values
    return float(np.corrcoef(ra, rb)[0, 1])


res = {}

# ---------------- A. COVID back-test ----------------
# Pre-2020 sample has only 36 quarters for a 10-variable VAR, so its lag dynamics are not
# reliable under an -88% shock (they explode). The back-test therefore checks what drives the
# ranking: each sector's impact exposure to a visitor shock, Sigma[j,v]/Sigma[v,v].
est = g_all.loc[:"2019Q4"]
c, Phi, S = fit_var1(est.values)
beta_pre = S[:, O] / S[O, O]
test_q = [q for q in g_all.index if "2020Q1" <= q <= "2022Q4"]
act_L = pd.DataFrame({n: [np.log(lv.loc[q, n] / lv.loc[f"2019Q{q[-1]}", n]) for q in test_q] for n in names}, index=test_q)
Lv = act_L["visitors"].mean()
pA = pd.Series(beta_pre * Lv, index=names)[others]
aA = act_L[others].mean()
# same test with the full-sample (2011-2026) model's exposures, for reference only (in-sample)
conn_ = json.load(open("out/connectedness.json"))
beta_full = np.array(conn_["girf_unit"]["visitors"][0])
pF = pd.Series(beta_full * Lv, index=names)[others]
res["covid"] = dict(
    estimation="2011Q1-2019Q4 (impact exposures)", test="2020Q1-2022Q4 average vs 2019", T_est=len(est), sectors=others,
    exposure_pre2020=[round(float(x), 3) for x in beta_pre[1:]],
    predicted_avg_change=[round(float(np.exp(x) - 1), 4) for x in pA],
    actual_avg_change=[round(float(np.exp(x) - 1), 4) for x in aA],
    visitors_actual_avg_change=round(float(np.exp(Lv) - 1), 4),
    spearman=round(spearman(pA, aA), 3),
    spearman_full_sample_in_sample=round(spearman(pF, aA), 3),
    mae_log=dict(model=round(float((pA - aA).abs().mean()), 3), no_contagion=round(float(aA.abs().mean()), 3),
                 proportional=round(float((Lv - aA).abs().mean()), 3)),
    note="Pre-2020, luxury retail moved with gaming (VIP era), not visitor numbers, so pre-2020 exposures of jewellery and clothing to visitors are near zero or negative.",
)

# ---------------- C. Recent out-of-sample ----------------
gw = g_all.clip(-WINSOR, WINSOR)
est = gw.loc[:"2024Q4"]
c, Phi, S = fit_var1(est.values)
test_q = [q for q in gw.index if "2025Q1" <= q <= "2026Q2"]
act = g_all.loc[test_q, names]
pred = pd.DataFrame(cond_forecast(c, Phi, S, est.values[-1], act["visitors"].values), index=test_q, columns=names)
# unconditional VAR forecast (no visitor information) as a benchmark
z, unc = est.values[-1].copy(), []
for _ in test_q:
    z = c + Phi @ z; unc.append(z.copy())
unc = pd.DataFrame(unc, index=test_q, columns=names)
rmse = lambda d: float(np.sqrt((d[others] ** 2).values.mean()))
dir_hit = float(((np.sign(pred[others]) == np.sign(act[others])) | (act[others].abs() < 0.02)).values.mean())
res["recent"] = dict(
    estimation="2011Q1-2024Q4", test="2025Q1-2026Q2", T_est=len(est),
    rmse=dict(model_with_visitors=round(rmse(pred - act), 4), var_without_visitors=round(rmse(unc - act), 4),
              no_change=round(rmse(act), 4), same_as_visitors=round(rmse(act.sub(act["visitors"], axis=0)), 4)),
    direction_hit_rate=round(dir_hit, 3),
    by_sector=[dict(sector=n, predicted=[round(x, 3) for x in pred[n]], actual=[round(x, 3) for x in act[n]]) for n in others],
    visitors_actual=[round(x, 3) for x in act["visitors"]], quarters=test_q,
)

# ---------------- D. Structural change ----------------
yr = lambda y: lv.loc[[f"{y}Q{i}" for i in range(1, 5)]].sum()
l19, l25 = yr(2019), yr(2025)
ratio = (l25 / l19)
ev = pd.read_csv("data/dsec_evidence_raw.csv", skiprows=1, header=None, names=["id", "year", "value", "unit"])
ev = ev.pivot(index="year", columns="id", values="value")
res["structure"] = dict(
    note="2025 annual totals relative to 2019",
    level_2025_vs_2019={n: round(float(ratio[n] - 1), 4) for n in names},
    tourism_ratio={"retail": {"2019": float(ev.loc[2019, 64214]), "2024": float(ev.loc[2024, 64214])},
                   "restaurants": {"2019": float(ev.loc[2019, 64216]), "2024": float(ev.loc[2024, 64216])}},
)

cal = json.load(open("out/calibration.json"))
res["current_exposure"] = dict(note="Share of a +/-1 visitor shock reaching each sector on impact: model (2011-2026) vs visitor share of 2025 sales (DSEC visitor spending by category x arrivals / retail sales)",
                               model=cal["derived"]["model_exposure"], visitor_share_2025=cal["derived"]["visitor_share_2025"])
json.dump(res, open("out/backtest.json", "w"), indent=1)

# ---------- print ----------
print("A. COVID back-test (avg change 2020-22 vs 2019): visitors actual", res["covid"]["visitors_actual_avg_change"])
for n, p, a in zip(others, res["covid"]["predicted_avg_change"], res["covid"]["actual_avg_change"]):
    print(f"   {n:24s} predicted {p:+.0%}  actual {a:+.0%}")
print("   spearman", res["covid"]["spearman"], "full-sample (in-sample)", res["covid"]["spearman_full_sample_in_sample"], "MAE", res["covid"]["mae_log"])
print("C. recent:", res["recent"]["rmse"], "direction hit", res["recent"]["direction_hit_rate"])
print("   visitors yoy", res["recent"]["visitors_actual"])
for r in res["recent"]["by_sector"]:
    print(f"   {r['sector']:24s} pred {r['predicted']}  act {r['actual']}")
print("D.", res["structure"])
print("E.", res["current_exposure"])
