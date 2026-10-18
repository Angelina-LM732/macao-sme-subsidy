"""Assemble the dashboard: inline model outputs and the simulation code into one HTML page."""
import json

conn = json.load(open("out/connectedness.json"))
cal = json.load(open("out/calibration.json"))
retrieved = open("data/retrieved_at.txt").read().strip()[:10]

meta = {
    "retrieved": retrieved,
    "sensitivity": json.load(open("out/sensitivity.json")),
    "backtest": json.load(open("out/backtest.json")),
    "tiered": json.load(open("out/tiered.json")),
    "varLabels": {
        "visitors": "Visitor arrivals", "gaming_ggr": "Gross gaming revenue", "hotel_guests": "Hotel guests",
        "visitor_fnb": "Visitor food & beverage spending", "jewellery_watches": "Retail · watches, clocks & jewellery",
        "leather_goods": "Retail · leather goods", "adult_clothing": "Retail · adults' clothing",
        "chinese_food_products": "Retail · Chinese food products", "supermarkets": "Retail · supermarkets",
        "pharmacies": "Retail · pharmacies"},
    "varShort": {
        "visitors": "Visitors", "gaming_ggr": "Gaming", "hotel_guests": "Hotels", "visitor_fnb": "Visitor F&B",
        "jewellery_watches": "Jewellery", "leather_goods": "Leather", "adult_clothing": "Clothing",
        "chinese_food_products": "Souvenir food", "supermarkets": "Supermarkets", "pharmacies": "Pharmacies"},
    "series": [
        dict(label="Visitor arrivals", dsec="Visitors by mode of transport: by sea + by land + by air", ids="14024 + 14028 + 14032",
             unit="persons · quarterly", use="Shock origin; 2020Q2 'by sea' blank in DSEC, treated as 0"),
        dict(label="Gross gaming revenue", dsec="Gaming › Gross gaming revenue › Total", ids="1216", unit="MOP million · quarterly",
             use="VAR variable; alternative shock origin"),
        dict(label="Hotel guests", dsec="Hotel establishments › No. of guests › Grand total", ids="25034", unit="guests · quarterly",
             use="VAR variable; alternative shock origin"),
        dict(label="Visitor F&B spending", dsec="Per-capita non-gaming spending by type of expense › Food & Beverage › Total, × visitor arrivals",
             ids="60283 × visitors", unit="MOP million · quarterly", use="Demand for tourist-facing restaurants; 2020Q2 per-capita blank, interpolated"),
        dict(label="Watches, clocks & jewellery", dsec="Retail sales › Watches, Clocks and Jewellery", ids="7006", unit="MOP million · quarterly", use="Sector demand"),
        dict(label="Leather goods", dsec="Retail sales › Leather Goods", ids="7032", unit="MOP million · quarterly", use="Sector demand"),
        dict(label="Adults' clothing", dsec="Retail sales › Adults' clothing", ids="7007", unit="MOP million · quarterly", use="Sector demand"),
        dict(label="Chinese food products", dsec="Retail sales › Chinese Food Products", ids="7036", unit="MOP million · quarterly", use="Souvenir-food shop demand"),
        dict(label="Supermarkets", dsec="Retail sales › Supermarkets", ids="7005", unit="MOP million · quarterly", use="Sector demand; local-demand proxy"),
        dict(label="Pharmacies", dsec="Retail sales › Pharmacies", ids="7038", unit="MOP million · quarterly", use="Sector demand"),
    ],
}

# ---------- Macao GDP per capita, for the health cost-effectiveness comparison ----------
GDP_URL = "https://yearbook.gcs.gov.mo/yearbook_pdf/2025/myb2025cAP24.pdf"
meta["gdp_pc"] = {"value": 587922, "year": 2024, "url": GDP_URL,
                  "source": "Macao Yearbook of Statistics 2025, Table 24 (DSEC)"}
meta["extra_sources"] = [
    dict(type="data", item="Macao GDP per capita, MOP 587,922 (2024, current prices)",
         basis="Benchmark for cost per DALY avoided (WHO-CHOICE 1-3x GDP per capita convention), health module only; does not enter the simulation.",
         source="Macao Yearbook of Statistics 2025, Table 24 (DSEC)", url=GDP_URL),
    dict(type="evidence", item="Cost-effectiveness threshold convention",
         basis="1-3x GDP per capita per DALY is a rough convention; WHO advises against using it alone.",
         source="Bertram et al. 2016, Bull World Health Organ 94:925-930", url="https://doi.org/10.2471/BLT.15.164418"),
    dict(type="data", item="Shop locations and tourist anchors for the 3D map",
         basis="1,015 shops in the model's sectors; restaurants within 200 m of 117 casinos, attractions, museums and heritage sites count as tourist-facing. Display only.",
         source="OpenStreetMap contributors (ODbL), Overpass API export 2026-10-18", url="https://www.openstreetmap.org/copyright"),
]

# ---------- trilingual titles (Traditional Chinese as used in Macao, Portuguese) ----------
meta["titles"] = {
    "hero": ["澳門中小企業銀行貸款利息補貼計劃", "Bonificação de juros de créditos bancários às PME"],
    "controls": ["情景設定", "Cenário"],
    "results": ["主要結果", "Resultados"],
    "map": ["風險分佈地圖", "Mapa de risco"],
    "ranking": ["優先扶持對象", "Perfis prioritários"],
    "hump": ["誰受益最多", "Quem ganha mais"],
    "design": ["分檔利率設計", "Taxas por escalões"],
    "applicant": ["申請人分檔", "Verificação do requerente"],
    "propagation": ["衝擊傳導", "Propagação do choque"],
    "network": ["行業關聯度", "Interligação dos setores"],
    "validation": ["澳門數據檢驗", "Validação com dados de Macau"],
    "health": ["健康模組", "Módulo de saúde"],
    "method": ["方法與資料來源", "Método e fontes"],
}
meta["sectorZh"] = {
    "restaurant_tourist": "餐飲（旅遊區）", "restaurant_local": "餐飲（社區）", "jewellery_watches": "珠寶鐘錶",
    "leather_goods": "皮具", "adult_clothing": "成人服裝", "chinese_food_products": "手信食品",
    "pharmacies": "藥房", "supermarkets": "超市雜貨"}

# ---------- 3D risk map: OpenStreetMap shop locations binned on a 200 m grid ----------
# data/osm_geodata.txt   : shops + coastline, Overpass API export (see README), delta-encoded in 1e-4 degrees
# data/osm_tourist_anchors.txt : casinos, tourist attractions and museums, heritage sites (OSM)
import math, collections
geo = open("data/osm_geodata.txt", encoding="utf-8").read().split("\n")
def dec(s):
    out, a, b = [], 0, 0
    for t in s.split(";"):
        x, y = t.split(" "); a += int(x); b += int(y); out.append((a / 1e4, b / 1e4))
    return out
LAT0, LON0 = 22.165, 113.555
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110574
xy = lambda la, lo: (round((lo - LON0) * KX), round((la - LAT0) * KY))
coast = [[c for p in dec(w) for c in xy(*p)] for w in geo[1][6:].split("|")]
tour_lines = open("data/osm_tourist_anchors.txt", encoding="utf-8").read().split("\n")
anchors = [xy(float(r.split(",")[1]), float(r.split(",")[2])) for r in tour_lines[1:] if r]
SECT = [s["key"] for s in cal["sectors"]]
CODE = {"J": "jewellery_watches", "L": "leather_goods", "C": "adult_clothing", "F": "chinese_food_products",
        "S": "supermarkets", "P": "pharmacies"}
TOUR_R, CELL = 200, 200
pts, cells = [], collections.defaultdict(lambda: [0] * len(SECT))
n_tour = n_rest = 0
for part in geo[2][4:].split("|"):
    code, rest = part.split(":", 1)
    for la, lo in dec(rest):
        x, y = xy(la, lo)
        if code == "R":
            near = min(math.hypot(x - a, y - b) for a, b in anchors) <= TOUR_R
            key = "restaurant_tourist" if near else "restaurant_local"; n_rest += 1; n_tour += near
        else:
            key = CODE[code]
        si = SECT.index(key)
        pts += [x, y, si]
        cells[(round(x / CELL), round(y / CELL))][si] += 1
osm_base = geo[0].split("osm_base=")[1].strip()
meta["map"] = {
    "cell": CELL, "origin": [LAT0, LON0], "coast": coast, "pts": pts,
    "cells": [[i * CELL, j * CELL] + c for (i, j), c in sorted(cells.items())],
    "n_shops": len(pts) // 3, "tour_radius": TOUR_R, "tour_share": round(n_tour / n_rest, 3),
    "n_anchors": len(anchors), "osm_base": osm_base, "anchors_base": tour_lines[0].split("base=")[1].strip(),
    "labels": [  # area names; landmark positions taken from the OSM anchor export
        dict(kind="area", zh="澳門半島", en="Macao Peninsula", pt="Península de Macau", p=xy(22.2125, 113.5470)),
        dict(kind="area", zh="氹仔", en="Taipa", pt="Taipa", p=xy(22.1600, 113.5640)),
        dict(kind="area", zh="路氹城", en="Cotai", pt="Cotai", p=xy(22.1375, 113.5660)),
        dict(kind="area", zh="路環", en="Coloane", pt="Coloane", p=xy(22.1190, 113.5560)),
        dict(kind="pin", zh="大三巴牌坊", en="Ruins of St. Paul's", p=xy(22.19746, 113.54086)),
        dict(kind="pin", zh="澳門歷史城區", en="Historic Centre", p=xy(22.19328, 113.54032)),
        dict(kind="pin", zh="媽閣廟", en="A-Ma Temple", p=xy(22.18607, 113.53127)),
        dict(kind="pin", zh="新葡京", en="Grand Lisboa", p=xy(22.19078, 113.54332)),
        dict(kind="pin", zh="漁人碼頭", en="Fisherman's Wharf", p=xy(22.19280, 113.55688)),
        dict(kind="pin", zh="威尼斯人", en="The Venetian", p=xy(22.14669, 113.56088)),
        dict(kind="pin", zh="澳門銀河", en="Galaxy Macau", p=xy(22.14748, 113.55444)),
        dict(kind="pin", zh="龍環葡韻", en="Taipa Houses", p=xy(22.15394, 113.55973)),
    ],
}
print("map:", meta["map"]["n_shops"], "shops,", len(meta["map"]["cells"]), "cells, tourist-facing restaurant share", meta["map"]["tour_share"])

# characters needed from the Chinese web font (Google Fonts 'text=' subset keeps the download small)
import urllib.parse
zh_chars = set()
for v in meta["titles"].values(): zh_chars |= set(v[0])
for v in meta["sectorZh"].values(): zh_chars |= set(v)
for l in meta["map"]["labels"]: zh_chars |= set(l["zh"])
zh_text = urllib.parse.quote("".join(sorted(c for c in zh_chars if ord(c) > 127)))

html = open("scripts/dashboard_template.html").read()
html = html.replace("__ZHTEXT__", zh_text)
# drop the template's own charset line and "build template" notice
html = html.split("-->\n", 1)[1] if html.startswith('<meta charset="utf-8">\n<!-- BUILD TEMPLATE') else html
sim = open("scripts/sim.js").read()
html = html.replace("/*__SIM__*/", sim)
html = html.replace("/*__CONN__*/null", json.dumps(conn, separators=(",", ":")))
html = html.replace("/*__CAL__*/null", json.dumps(cal, separators=(",", ":")))
html = html.replace("/*__META__*/null", json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
assert "__CONN__" not in html and "__SIM__" not in html

# Encoding safety: declare UTF-8 AND make the file pure ASCII, so it renders identically
# even when a browser guesses another encoding (e.g. GBK on Chinese-locale systems).
import re
def esc_js(s):   return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in s)
def esc_css(s):  return "".join(c if ord(c) < 128 else "\\%06x" % ord(c) for c in s)
def esc_html(s): return "".join(c if ord(c) < 128 else "&#x%x;" % ord(c) for c in s)
out, pos = [], 0
for m in re.finditer(r"(<script[^>]*>)(.*?)(</script>)|(<style[^>]*>)(.*?)(</style>)", html, re.S):
    out.append(esc_html(html[pos:m.start()]))
    if m.group(1): out.append(m.group(1) + esc_js(m.group(2)) + m.group(3))
    else: out.append(m.group(4) + esc_css(m.group(5)) + m.group(6))
    pos = m.end()
out.append(esc_html(html[pos:]))
html = '<meta charset="utf-8">\n' + "".join(out)
assert all(ord(c) < 128 for c in html), "non-ASCII left"
open("dashboard.html", "w", encoding="ascii").write(html)
print("bytes", len(html.encode()), "pure ASCII")
