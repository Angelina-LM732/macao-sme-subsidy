"""Stage 0: build the quarterly panel from raw DSEC downloads.

Input : data/dsec_quarterly_raw.csv  (indicator_id, period, value, remark) fetched from
        the DSEC Time Series Database API, endpoint
        https://www.dsec.gov.mo/TimeSeriesApi/App/IndicatorValue/LatestSameEndPeriodv3
Output: data/panel_levels.csv  (quarterly levels, one column per model variable)
        data/panel_growth.csv  (year-on-year log growth used in the VAR)
"""
import pandas as pd, numpy as np, json

RAW = "data/dsec_quarterly_raw.csv"
raw = pd.read_csv(RAW, skiprows=1, header=None, names=["id", "period", "value", "remark"])
wide = raw.pivot(index="period", columns="id", values="value").sort_index()

# --- derived series (every input is a DSEC indicator, see SOURCES in sources.json) ---
lv = pd.DataFrame(index=wide.index)
# Visitor arrivals = by sea (14024) + by land (14028) + by air (14032).
# 2020Q2 'by sea' is blank in DSEC (ferries suspended) -> treated as 0.
lv["visitors"] = wide[14024].fillna(0) + wide[14028] + wide[14032]
lv["gaming_ggr"] = wide[1216]                      # Gross gaming revenue, MOP mn
lv["hotel_guests"] = wide[25034]                   # Hotel establishments, no. of guests
# Visitor food & beverage spending = per-capita F&B spending (60283, MOP) x visitor arrivals.
# 2020Q2 per-capita value is blank (survey suspended) -> linear interpolation, flagged.
fb_pc = wide[60283].astype(float)
fb_pc_interp = fb_pc.interpolate(limit_area="inside")
lv["visitor_fnb"] = fb_pc_interp * lv["visitors"] / 1e6   # MOP mn
lv["jewellery_watches"] = wide[7006]
lv["leather_goods"] = wide[7032]
lv["adult_clothing"] = wide[7007]
lv["chinese_food_products"] = wide[7036]
lv["supermarkets"] = wide[7005]
lv["pharmacies"] = wide[7038]

lv = lv.loc["2010Q1":]                 # F&B spending starts 2010Q1
assert lv.notna().all().all(), lv[lv.isna().any(axis=1)]
lv.to_csv("data/panel_levels.csv")

# year-on-year log growth (removes seasonality without a seasonal model)
g = np.log(lv).diff(4).dropna()
g.to_csv("data/panel_growth.csv")

flags = {
    "visitors_2020Q2_sea_blank_as_zero": True,
    "fnb_per_capita_2020Q2_interpolated": float(fb_pc_interp.loc["2020Q2"]),
    "sample_growth": [g.index[0], g.index[-1], len(g)],
}
json.dump(flags, open("data/prep_flags.json", "w"), indent=1)
print(lv.tail(3).round(0).to_string())
print(g.describe().T[["min", "max", "std"]].round(2).to_string())
print(flags)
