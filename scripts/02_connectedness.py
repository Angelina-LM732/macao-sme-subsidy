"""Stage 1-2: VAR, Diebold-Yilmaz (2012) generalized connectedness, generalized impulse
responses (Pesaran & Shin 1998) and bootstrap noise paths for the cash-flow simulation.

Implemented directly in numpy (no statsmodels) so every step is visible.
Input : data/panel_growth.csv (yoy log growth, 2011Q1-2026Q2)
Output: out/connectedness.json
"""
import numpy as np, pandas as pd, json, os

os.makedirs("out", exist_ok=True)
H = 8            # forecast horizon (quarters) for variance decomposition
WINSOR = 1.0     # winsorise yoy log growth at +/-1.0 (=-63% / +172%) in the main spec
ROLL = 24        # rolling window length (quarters)
NPATH = 600      # bootstrap noise paths
rng = np.random.default_rng(20261008)

g_raw = pd.read_csv("data/panel_growth.csv", index_col=0)
names = list(g_raw.columns)
N = len(names)


def fit_var(Y, p):
    """OLS VAR(p) with constant. Y: T x N. Returns coefs (N x (1+Np)), residuals, Sigma."""
    T = Y.shape[0]
    X = np.hstack([np.ones((T - p, 1))] + [Y[p - l - 1:T - l - 1] for l in range(p)])
    Yt = Y[p:]
    B, *_ = np.linalg.lstsq(X, Yt, rcond=None)
    U = Yt - X @ B
    k = X.shape[1]
    Sigma = U.T @ U / (Yt.shape[0] - k)
    return B.T, U, Sigma


def bic(Y, p):
    _, U, _ = fit_var(Y, p)
    T = U.shape[0]
    S = U.T @ U / T
    return np.log(np.linalg.det(S)) + np.log(T) * (N * N * p) / T


def ma_coefs(B, p, h):
    """MA matrices A_0..A_{h-1} from VAR coefficients (companion recursion)."""
    Phi = [B[:, 1 + l * N:1 + (l + 1) * N] for l in range(p)]
    A = [np.eye(N)]
    for s in range(1, h):
        A.append(sum(Phi[l] @ A[s - l - 1] for l in range(min(p, s))))
    return A


def gfevd(A, Sigma):
    """Generalized FEVD, row-normalised (Diebold & Yilmaz 2012). theta[i,j]: share of i's
    H-step forecast-error variance due to shocks in j."""
    num = np.zeros((N, N)); den = np.zeros(N)
    sd = np.diag(Sigma)
    for Ah in A:
        M = Ah @ Sigma
        num += M ** 2 / sd[None, :]
        den += np.diag(Ah @ Sigma @ Ah.T)
    th = num / den[:, None]
    return th / th.sum(axis=1, keepdims=True)


def dy_table(th):
    off = th - np.diag(np.diag(th))
    frm = off.sum(axis=1) * 100          # FROM others (row sums)
    to = off.sum(axis=0) * 100           # TO others (column sums)
    total = off.sum() / N * 100
    return dict(total=total, to=to, frm=frm, net=to - frm, pairwise_net=(off.T - off) * 100)


def girf(A, Sigma, j, size):
    """Response of all variables to a shock of `size` (units of variable j) in variable j."""
    return np.array([Ah @ Sigma[:, j] / Sigma[j, j] * size for Ah in A])  # h x N


def run(g, label, p=None):
    Y = g.values.astype(float)
    if p is None:
        p = min((1, 2), key=lambda q: bic(Y, q))
    B, U, Sigma = fit_var(Y, p)
    A = ma_coefs(B, p, H)
    th = gfevd(A, Sigma)
    t = dy_table(th)
    eig = np.max(np.abs(np.linalg.eigvals(B[:, 1:1 + N]))) if p == 1 else None
    print(f"{label}: p={p}, T={len(Y)}, total connectedness={t['total']:.1f}%",
          f"max|eig|={eig:.2f}" if eig else "")
    return dict(p=p, B=B, U=U, Sigma=Sigma, A=A, theta=th, dy=t, T=len(Y))


# ---------- main and robustness specifications ----------
g_w = g_raw.clip(-WINSOR, WINSOR)
main = run(g_w, "MAIN winsorised 2011Q1-2026Q2")
raw = run(g_raw, "ROBUST raw (no winsorising)")
pre = run(g_raw.loc[:"2019Q4"], "ROBUST pre-COVID 2011Q1-2019Q4", p=1)
bic_table = {p: bic(g_w.values, p) for p in (1, 2)}

# ---------- rolling total connectedness (main transform, VAR(1)) ----------
roll = []
for end in range(ROLL, len(g_w) + 1):
    sub = g_w.iloc[end - ROLL:end].values
    B, U, S = fit_var(sub, 1)
    th = gfevd(ma_coefs(B, 1, H), S)
    roll.append([g_w.index[end - 1], round(dy_table(th)["total"], 2)])

# ---------- generalized impulse responses per unit (1.0 log-point) shock ----------
origins = ["visitors", "gaming_ggr", "hotel_guests"]
girfs = {o: girf(main["A"], main["Sigma"], names.index(o), 1.0).round(5).tolist() for o in origins}

# ---------- bootstrap 'normal-times' noise paths ----------
# Residuals are resampled jointly (whole rows) so cross-sector correlation is kept.
# COVID-era residuals (2020Q1-2023Q4) are excluded: the shock scenario supplies the crisis,
# the noise represents ordinary quarter-to-quarter uncertainty.
res_idx = g_w.index[main["p"]:]
U = main["U"]
keep = ~((res_idx >= "2020Q1") & (res_idx <= "2023Q4"))
U_n = U[keep] - U[keep].mean(axis=0)
Phi1 = main["B"][:, 1:1 + N]
paths = np.zeros((NPATH, H, N))
for k in range(NPATH):
    z = np.zeros(N)
    for h in range(H):
        z = Phi1 @ z + U_n[rng.integers(len(U_n))]
        paths[k, h] = z
# growth -> level deviation from normal: L_h = g_h + L_{h-4}
for h in range(4, H):
    paths[:, h] += paths[:, h - 4]

out = dict(
    variables=names, horizon=H, winsor=WINSOR, sample=[g_w.index[0], g_w.index[-1]],
    var_lag=main["p"], T=main["T"], bic={str(k): round(v, 3) for k, v in bic_table.items()},
    theta=(main["theta"] * 100).round(2).tolist(),
    total=round(main["dy"]["total"], 2),
    to=main["dy"]["to"].round(2).tolist(), frm=main["dy"]["frm"].round(2).tolist(),
    net=main["dy"]["net"].round(2).tolist(),
    pairwise_net=main["dy"]["pairwise_net"].round(2).tolist(),
    robustness=dict(raw_total=round(raw["dy"]["total"], 2), raw_net=raw["dy"]["net"].round(2).tolist(),
                    precovid_total=round(pre["dy"]["total"], 2), precovid_net=pre["dy"]["net"].round(2).tolist(),
                    precovid_T=pre["T"]),
    rolling=roll, rolling_window=ROLL,
    girf_unit=girfs,
    residual_sd=np.sqrt(np.diag(main["Sigma"])).round(4).tolist(),
    noise_paths=paths.round(4).tolist(), noise_note="bootstrap of non-COVID residuals, VAR(1) propagation, converted to log-level deviations",
    noise_n_residuals=int(keep.sum()),
)
json.dump(out, open("out/connectedness.json", "w"))

# readable summary
tab = pd.DataFrame({"TO": out["to"], "FROM": out["frm"], "NET": out["net"],
                    "NET_raw": out["robustness"]["raw_net"], "NET_precovid": out["robustness"]["precovid_net"]},
                   index=names)
print(tab.round(1).to_string())
print("BIC", bic_table)
print("GIRF visitors -1.0 -> h0..h3 (first 4 vars):")
print(pd.DataFrame(girfs["visitors"], columns=names).iloc[:4].round(2).to_string())
print("rolling:", roll[0], roll[len(roll)//2], roll[-1], "max", max(roll, key=lambda r: r[1]))
