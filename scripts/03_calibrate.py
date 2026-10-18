"""Stage 3a: calibrate SME cost structures from DSEC annual surveys (reference year 2024)
and write every model parameter, with its source, to out/calibration.json.
"""
import pandas as pd, json

a = pd.read_csv("data/dsec_annual_raw.csv", skiprows=1, header=None, names=["id", "year", "value", "unit"])
v = a.pivot(index="year", columns="id", values="value")
Y = 2024

def struct(rec, pur, comp, opex, persons, est, label, ids):
    rec, pur, comp, opex = (v.loc[Y, i] for i in (rec, pur, comp, opex))
    return dict(
        label=label,
        cogs_share=round(pur / rec, 4),                 # variable cost share of revenue
        wage_share=round(comp / rec, 4),
        opex_share=round(opex / rec, 4),
        margin=round(1 - (pur + comp + opex) / rec, 4),  # implied operating margin
        rev_per_worker_month=round(rec * 1000 / v.loc[Y, persons] / 12, 0),  # MOP
        workers_per_est=round(v.loc[Y, persons] / v.loc[Y, est], 2),
        dsec_ids=ids, year=Y)

cost = {
    "retail": struct(8547, 8546, 8544, 8545, 8543, 8542, "Retail trade establishments",
                     [8542, 8543, 8544, 8545, 8546, 8547]),
    "restaurant": struct(30095, 30089, 30077, 30083, 30071, 30065, "Restaurants and similar establishments",
                         [30065, 30071, 30077, 30083, 30089, 30095]),
}

# Sector -> demand series (VAR variable) and cost structure
# ---------- evidence used to set parameters (all computed here, not typed in) ----------
ev = pd.read_csv("data/dsec_evidence_raw.csv", skiprows=1, header=None, names=["id", "year", "value", "unit"])
ev = ev.pivot(index="year", columns="id", values="value")
tourism_ratio_rest = ev.loc[2024, 64216] / 100      # DSEC TSA: tourism ratio, restaurants & similar, 2024
# Two restaurant types whose average equals the industry tourism ratio:
# tourist-facing = 100% visitor demand, neighbourhood = 2*ratio - 1
neigh_share = round(2 * tourism_ratio_rest - 1, 3)

# Margin profiles: +/- one s.d. of each sector's DSEC aggregate margin, 2015-2024
yrs = range(2015, 2025)
marg = pd.DataFrame({
    "retail": [1 - (v.loc[y, 8546] + v.loc[y, 8544] + v.loc[y, 8545]) / v.loc[y, 8547] for y in yrs],
    "restaurant": [1 - (v.loc[y, 30089] + v.loc[y, 30077] + v.loc[y, 30083]) / v.loc[y, 30095] for y in yrs]}, index=yrs)
margin_sd = marg.std().round(4).to_dict()

# Loan size: scheme's average approved loan / average establishment's monthly fixed cost (DSEC 2024)
SCHEME_LOANS_MOP, SCHEME_APPROVED, SCHEME_SUBSIDY_MOP = 3.8e9, 1682, 4.6e8   # DSEDT reply, 21 Jan 2026
est_r, est_f = v.loc[Y, 8542], v.loc[Y, 30065]
fix_r = (v.loc[Y, 8544] + v.loc[Y, 8545]) * 1000 / est_r / 12
fix_f = (v.loc[Y, 30077] + v.loc[Y, 30083]) * 1000 / est_f / 12
avg_fixed = (est_r * fix_r + est_f * fix_f) / (est_r + est_f)
avg_loan = SCHEME_LOANS_MOP / SCHEME_APPROVED
loan_months = round(avg_loan / avg_fixed)

# Baseline working-age mortality: UN WPP 2024 adult mortality 45q15 for Macao = 38.8 per 1,000
q45_15 = 0.0388
base_mort = round(1 - (1 - q45_15) ** (1 / 45), 5)
# Depression after job loss: Korea Welfare Panel, permanent -> unemployed, OR 1.78 (Yoo et al. 2016, BMJ Open)
# converted to excess prevalence on Paul & Moser's 16% baseline among the employed
OR_KR, P_EMP = 1.78, 0.16
p_unemp_kr = P_EMP * OR_KR / (1 - P_EMP + P_EMP * OR_KR)
excess_psych_kr = round(p_unemp_kr - P_EMP, 4)

# Years of life lost per excess death: DSEC life expectancy at birth 2022-2025 (83.5) minus age 40,
# the displacement age Sullivan & von Wachter use for their life-expectancy illustration
le0 = 83.5
yll = round(le0 - 40, 1)

# Current (post-reopening) exposure: visitor spending by category x visitor arrivals, divided by
# retail sales of the matching category, 2025. Only categories that map one-to-one are used.
rawq = pd.read_csv("data/dsec_quarterly_raw.csv", skiprows=1, header=None, names=["id", "p", "v", "r"]).pivot(index="p", columns="id", values="v")
spq = pd.read_csv("data/dsec_visitor_spending_raw.csv", skiprows=1, header=None, names=["id", "p", "v"]).pivot(index="p", columns="id", values="v")
visq = rawq[14024].fillna(0) + rawq[14028] + rawq[14032]
q25 = [f"2025Q{i}" for i in range(1, 5)]
share_map = {"jewellery_watches": (60332, [7006]), "leather_goods": (60380, [7032, 7031]), "adult_clothing": (60316, [7007])}
visitor_share_2025 = {k: round(float((spq.loc[q25, cid] * visq[q25]).sum() / 1e6 / rawq.loc[q25, rids].sum().sum()), 3)
                      for k, (cid, rids) in share_map.items()}
conn_ = json.load(open("out/connectedness.json"))
g0 = dict(zip(conn_["variables"], conn_["girf_unit"]["visitors"][0]))
exposure_scale_2025 = {k: round(visitor_share_2025[k] / g0[k], 3) for k in visitor_share_2025}

sectors = [
    dict(key="restaurant_tourist", name="Restaurant (tourist-facing)", zh="餐饮（游客区）", cost="restaurant",
         mix={"visitor_fnb": 1.0}, mix_note="DSEC visitor F&B spending series"),
    dict(key="restaurant_local", name="Restaurant (neighbourhood)", zh="餐饮（社区）", cost="restaurant",
         mix={"visitor_fnb": neigh_share, "supermarkets": round(1 - neigh_share, 3)},
         mix_note=f"visitor share {neigh_share:.0%}: the two restaurant types average to the DSEC tourism ratio {tourism_ratio_rest:.1%} (2024)"),
    dict(key="jewellery_watches", name="Jewellery & watches", zh="珠宝钟表", cost="retail", mix={"jewellery_watches": 1.0}),
    dict(key="leather_goods", name="Leather goods", zh="皮具", cost="retail", mix={"leather_goods": 1.0}),
    dict(key="adult_clothing", name="Clothing", zh="成人服装", cost="retail", mix={"adult_clothing": 1.0}),
    dict(key="chinese_food_products", name="Souvenir food (Chinese food products)", zh="手信食品", cost="retail",
         mix={"chinese_food_products": 1.0}),
    dict(key="pharmacies", name="Pharmacy", zh="药房", cost="retail", mix={"pharmacies": 1.0}),
    dict(key="supermarkets", name="Supermarket / grocery", zh="超市杂货", cost="retail", mix={"supermarkets": 1.0}),
]

params = {
    # --- policy anchor: SME Bank Loan Interest Subsidy Scheme (DSEDT) ---
    "subsidy_rate": 0.04, "loan_cap": 5_000_000, "subsidy_term_months": 36, "max_employees": 100,
    # --- financing ---
    "prime_rate": 0.0525, "loan_spread": 0.01,
    "loan_months_of_fixed_cost": loan_months, "interest_only": True, "proceeds_as_cash": False,
    # --- simulation ---
    "horizon_months": 24, "idio_sd": 0.0, "idio_rho": 0.0,     # no firm-level noise: heterogeneity comes from the profile grid
    "validation_delinquency": 0.085,                           # AMCM SME delinquency ratio, end-June 2026 (validation only)
    "default_shock_pct": -25, "default_origin": "visitors", "default_duration_q": 4, "default_recovery_q": 4,
    # --- profile grid ---
    "sizes": [3, 10, 40], "buffers": [13, 27, 62], "buffer_in_days": True,
    "margin_sd": margin_sd, "margin_shifts": [-margin_sd["retail"], 0.0, margin_sd["retail"]],
    # --- health module ---
    "excess_psych_prev": excess_psych_kr, "excess_psych_prev_intl": 0.18, "dw_depression": 0.396, "psych_duration_years": 0.5,
    "baseline_mortality": base_mort, "excess_mortality_rr": 0.5, "yll_per_death": yll,
}

derived = dict(tourism_ratio_restaurants_2024=tourism_ratio_rest, neighbourhood_visitor_share=neigh_share,
               margins_by_year={str(k): {c: round(marg.loc[k, c], 4) for c in marg} for k in marg.index},
               avg_scheme_loan=round(avg_loan), avg_fixed_cost_per_establishment=round(avg_fixed),
               loan_months_exact=round(avg_loan / avg_fixed, 2),
               subsidy_to_loan_ratio=round(SCHEME_SUBSIDY_MOP / SCHEME_LOANS_MOP, 3),
               baseline_mortality_from_45q15=base_mort, yll=yll,
               visitor_share_2025=visitor_share_2025, model_exposure=({k: round(g0[k], 3) for k in visitor_share_2025}),
               exposure_scale_2025=exposure_scale_2025,
               depression_korea=dict(odds_ratio=OR_KR, baseline=P_EMP, unemployed=round(p_unemp_kr, 4), excess=excess_psych_kr))

sources = [
    dict(item="Subsidy 4% p.a., loan cap MOP 5m, up to 3 years, SME with at most 100 staff, MOP 10bn pool",
         basis="Scheme terms", source="Macao News on the DSEDT scheme",
         url="https://macaonews.org/news/business/macau-sme-loans-economy-macao/", type="policy"),
    dict(item="Scheme continued in the 2026 Policy Address (18 Nov 2025)", basis="Policy anchor",
         source="HRO summary of the 2026 Policy Address",
         url="https://www.humanresourcesonline.net/key-highlights-from-macao-s-2026-policy-address", type="policy"),
    dict(item="Prime rate 5.25% p.a.",
         basis="Latest bank notice found (ICBC Macau, effective 3 Nov 2025; HSBC had cut to 5.375% on 24 Sep 2025). AMCM composite funding cost barely moved in 2026 (1.16% to 1.15%, Q1 to Q2), so no sign of a further cut.",
         source="ICBC (Macau) notice; AMCM composite interest rate Q2 2026",
         url="https://v.icbc.com.cn/userfiles/resources/icbc/haiwai/icbc_macau/pdf/2025/notice_1031.pdf", type="finance"),
    dict(item="Bank rate = prime + 1.0pp",
         basis="Only 45% of new SME credit is collateralised (AMCM, H1 2026), so most SME credit is unsecured and priced above prime. The subsidy pays the full 4% either way; the spread only changes the part firms pay, and the sensitivity table shows results barely move between +0 and +3pp.",
         source="AMCM SME credit, H1 2026", url="https://www.gov.mo/en/?p=406590", type="calibrated"),
    dict(item=f"Loan size = {loan_months} months of fixed costs (cap MOP 5m)",
         basis=f"Scheme average loan MOP {avg_loan/1e6:.2f}m (MOP 3.8bn over 1,682 approvals, to 21 Jan 2026) divided by the average establishment's monthly fixed cost MOP {avg_fixed/1e3:.0f}k (DSEC 2024 retail and restaurant surveys) = {avg_loan/avg_fixed:.1f} months.",
         source="DSEDT reply to the Legislative Assembly, Feb 2026",
         url="https://al.gov.mo/uploads/attachment/2026-02/d1eb1ecf3391a55ca2a290b18ce30038.pdf", type="calibrated"),
    dict(item="Loans are interest-only credit lines, already drawn and spent",
         basis="AMCM reports SME lending as credit limits with an 84.1% utilisation rate, i.e. mostly revolving lines that are drawn and used, so loan proceeds are not counted as spare cash; the firm carries the debt and the subsidy cuts its interest bill. DSEDT's approved subsidy (MOP 460m on MOP 3.8bn = 12.1%) equals 4% x 3 years on the full balance.",
         source="AMCM SME credit, H1 2026; DSEDT reply, Feb 2026", url="https://www.gov.mo/en/?p=406590", type="calibrated"),
    dict(item="Cash buffer profiles: 13 / 27 / 62 days of normal outflows",
         basis="25th percentile, median and 75th percentile cash buffer days of 600,000 US small businesses (restaurants' median: 16 days). No comparable distribution is published for Macao or Hong Kong SMEs (a 2020 HKGCC poll only reports that 42% of SMEs expected to last up to six months without relief), so the sensitivity table halves and doubles these buffers.",
         source="JPMorgan Chase Institute, Cash Flows, Balances, and Buffer Days (2016)",
         url="https://www.jpmorganchase.com/institute/all-topics/business-growth-and-entrepreneurship/report-cash-flows-balances-and-buffer-days",
         type="evidence"),
    dict(item=f"Margin profiles: sector margin -/+ {margin_sd['retail']*100:.1f}pp (retail), -/+ {margin_sd['restaurant']*100:.1f}pp (restaurants)",
         basis="One standard deviation of each sector's aggregate margin across DSEC survey years 2015-2024, so a weak or strong profile looks like the sector in a bad or good year.",
         source="DSEC retail and restaurant surveys (IDs 8544-8547, 30077-30095)", url="", type="data"),
    dict(item="No separate firm-level revenue noise",
         basis="Revenue uncertainty comes only from DSEC sector data (bootstrapped VAR residuals); firm differences come from the margin and cash-buffer profiles. Adding 8% monthly firm noise changed normal-times failure by only 0.3pp, so it was removed rather than assumed.",
         source="Model test", url="", type="calibrated"),
    dict(item="Validation: normal-times failure",
         basis="With no shock and no subsidy, the average profile's 24-month failure rate is VALIDATION_FAILURE, against an SME loan delinquency ratio of 8.5% at end-June 2026. Same order of magnitude; the model is somewhat pessimistic because restaurant profiles inherit the sector's negative 2024 margin.",
         source="AMCM SME credit, H1 2026", url="https://www.gov.mo/en/?p=406590", type="calibrated"),
    dict(item=f"Neighbourhood restaurants: {neigh_share:.0%} visitor demand, rest local (supermarket sales as proxy)",
         basis=f"DSEC Tourism Satellite Account: visitors account for {tourism_ratio_rest:.1%} of restaurant value added (2024). With tourist-facing restaurants at 100%, the neighbourhood type is set so the two average to the industry figure.",
         source="DSEC Tourism Satellite Account, ID 64216", url="", type="data"),
    dict(item="Staff sizes 3 / 10 / 40",
         basis="DSEC 2024 averages are 5.4 persons per retail and 7.7 per restaurant establishment; 40 represents larger SMEs under the scheme's 100-staff limit.",
         source="DSEC retail and restaurant surveys (IDs 8542-8543, 30065, 30071)", url="", type="data"),
    dict(item=f"Excess depression after job loss: {excess_psych_kr*100:.1f} percentage points",
         basis=f"East Asian evidence used as the default: in the Korea Welfare Panel (7,368 adults), moving from permanent work to unemployment raised the odds of depression 1.78 times. Applied to the 16% baseline among the employed, that is {p_unemp_kr*100:.1f}% vs 16%. The international meta-analysis (34% vs 16%, i.e. 18 points) is kept as the upper comparator.",
         source="Yoo et al. (2016), BMJ Open 6(3):e008570; Paul & Moser (2009)", url="https://bmjopen.bmj.com/content/6/3/e008570", type="evidence"),
    dict(item="Disability weight 0.396 (moderate depressive episode)",
         basis="GBD 2013 weights", source="Population Health Metrics 2021, Table 2",
         url="https://pophealthmetrics.biomedcentral.com/articles/10.1186/s12963-021-00253-4/tables/2", type="evidence"),
    dict(item="Episode length 0.5 years",
         basis="Median duration of a major depressive episode in the general population is 6 months (mean 10.7 months).",
         source="ten Have et al. (2017), Acta Psychiatrica Scandinavica 136(3)",
         url="https://research-portal.uu.nl/en/publications/duration-of-major-and-minor-depressive-episodes-and-associated-ri/", type="evidence"),
    dict(item="Excess mortality +50% in the year after job loss",
         basis="Two independent sources agree: the lower bound of the 50-100% US estimate, and the international meta-analysis of 42 studies (20 million people), pooled HR 1.63, about 24% lower (roughly 1.48) once health behaviours are controlled. No usable East Asian estimate was found; HR 1.63 is in the sensitivity table.",
         source="Roelfs et al. (2011), Soc Sci Med 72(6); Sullivan & von Wachter (2009)",
         url="https://researchconnect.suny.edu/en/publications/losing-life-and-livelihood-a-systematic-review-and-meta-analysis-/", type="evidence"),
    dict(item=f"Baseline working-age mortality {base_mort*100:.3f}% a year",
         basis="Macao's probability of dying between 15 and 60 is 38.8 per 1,000 (UN World Population Prospects 2024), spread evenly over 45 years.",
         source="UN WPP 2024 via MeasuredWorld", url="https://measuredworld.com/countries/macao/mortality/adult-mortality", type="evidence"),
    dict(item=f"{yll} years of life lost per excess death",
         basis="DSEC life expectancy at birth 2022-2025 is 83.5 years; minus 40, the displacement age Sullivan & von Wachter use for their life-expectancy illustration.",
         source="DSEC Time Series Database, ID 20001", url="", type="data"),
]

json.dump(dict(cost=cost, sectors=sectors, params=params, derived=derived, sources=sources),
          open("out/calibration.json", "w"), indent=1)
for k, c in cost.items():
    print(k, {x: c[x] for x in ("cogs_share", "wage_share", "opex_share", "margin", "rev_per_worker_month", "workers_per_est")})
print(json.dumps(derived, indent=0)[:1500])
