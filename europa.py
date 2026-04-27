"""
Europa-sjekker og sammenlignings-side.
Henter pris/availability for Europa-ruter og rendrer en oversiktlig tabell.

Kjør:  python europa.py
Output: output/europa.html
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from urllib.parse import urlencode

import requests
from jinja2 import Template

import config

log = logging.getLogger("europa")

# Europa-destinasjoner som er aktuelle (mamma + Jonas)
EUROPA_DESTINATIONS = [
    # Hoved-byer
    ("CDG", "Paris"),       ("AMS", "Amsterdam"),  ("LHR", "London"),
    ("FCO", "Roma"),        ("MXP", "Milano"),     ("MAD", "Madrid"),
    ("BCN", "Barcelona"),   ("MUC", "München"),    ("FRA", "Frankfurt"),
    ("ZRH", "Zürich"),      ("VIE", "Wien"),       ("ATH", "Athen"),
    ("LIS", "Lisboa"),      ("DUB", "Dublin"),     ("EDI", "Edinburgh"),
    # Ferie / varme
    ("AGP", "Málaga"),      ("PMI", "Palma"),      ("LCA", "Larnaca"),
    ("HER", "Heraklion"),   ("GZP", "Antalya"),    ("MLA", "Malta"),
    ("OPO", "Porto"),       ("SVQ", "Sevilla"),    ("FNC", "Madeira"),
    # Øst
    ("PRG", "Praha"),       ("BUD", "Budapest"),   ("WAW", "Warszawa"),
    ("VNO", "Vilnius"),     ("RIX", "Riga"),       ("TLL", "Tallinn"),
    ("IST", "Istanbul"),
]

ORIGINS = ["OSL", "CPH", "ARN"]


def _query(origin: str, dest: str) -> dict | None:
    if not config.SEATS_AERO_KEY:
        return None
    try:
        r = requests.get(
            "https://seats.aero/partnerapi/availability",
            params={
                "origin_airport": origin, "destination_airport": dest,
                "source": "eurobonus",
                "start_date": "2026-06-01", "end_date": "2027-12-31",
                "take": 500,
            },
            headers={"Partner-Authorization": config.SEATS_AERO_KEY},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    recs = r.json().get("data") or []
    if not recs:
        return None

    j_dates = [x for x in recs if int(x.get("JRemainingSeats", 0)) >= 2]
    j1_dates = [x for x in recs if int(x.get("JRemainingSeats", 0)) >= 1]
    y_dates = [x for x in recs if int(x.get("YRemainingSeats", 0)) >= 1]

    j_cost = min((int(x.get("JMileageCostRaw") or 0) for x in j_dates),
                 default=int(j1_dates[0].get("JMileageCostRaw") or 0) if j1_dates else 0)
    y_cost = min((int(x.get("YMileageCostRaw") or 0) for x in y_dates), default=0)
    j_first = j_dates[0]["Date"] if j_dates else None
    y_first = y_dates[0]["Date"] if y_dates else None

    return {
        "total": len(recs),
        "j_2plus": len(j_dates),
        "j_1plus": len(j1_dates),
        "y_avail": len(y_dates),
        "j_cost": j_cost,
        "y_cost": y_cost,
        "j_first": j_first,
        "y_first": y_first,
    }


def fetch_all() -> dict:
    """Returner {origin: {dest: stats}}."""
    out: dict[str, dict] = {}
    for origin in ORIGINS:
        out[origin] = {}
        for dest, _ in EUROPA_DESTINATIONS:
            stats = _query(origin, dest)
            if stats:
                out[origin][dest] = stats
                log.info("EU %s-%s: %dd, J:%d Y:%d (J@%d Y@%d)",
                         origin, dest, stats["total"], stats["j_2plus"], stats["y_avail"],
                         stats["j_cost"], stats["y_cost"])
    return out


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #

TEMPLATE = Template("""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>Europa-priser — SAS EuroBonus</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #FAF7F2; --ink: #5C4B3A; --muted: #8a7a66;
    --line: #e5ddd0; --card: #ffffff; --gold: #b58a4e;
    --green: #4a6f4a; --red: #a3565b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 32px 16px; background: var(--bg); color: var(--ink);
    font: 16px/1.55 Georgia, "EB Garamond", Garamond, serif;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  h1 { font-weight: 600; font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }
  .meta { color: var(--muted); font-size: 14px; margin: 0 0 24px; }
  .meta a { color: var(--ink); }
  h2 {
    font-weight: 600; font-size: 14px; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--muted);
    margin: 32px 0 12px; border-bottom: 1px solid var(--line); padding-bottom: 6px;
  }
  table {
    width: 100%; border-collapse: collapse; font-size: 13px;
    background: var(--card); border-radius: 8px; overflow: hidden;
    font-family: -apple-system, sans-serif;
  }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); }
  th {
    color: var(--muted); font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.05em;
    background: var(--bg);
  }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td.dest { font-weight: 600; }
  td.cost { color: var(--gold); font-weight: 600; }
  td.cost.cheap { color: var(--green); }
  td.cost.expensive { color: var(--red); }
  td.dates { color: var(--muted); }
  tr:hover { background: rgba(181,138,78,0.04); }
  .badge {
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    font-size: 10px; background: var(--bg); border: 1px solid var(--line);
    color: var(--muted);
  }
  .badge.good { background: #e8eee4; color: var(--green); border-color: var(--green); }
  .legend { font-size: 12px; color: var(--muted); margin: 16px 0; font-family: -apple-system, sans-serif; }
  .legend span { margin-right: 14px; }
  .booknow {
    display: inline-block; background: var(--ink); color: var(--bg);
    padding: 4px 10px; border-radius: 4px; text-decoration: none;
    font: 600 11px -apple-system, sans-serif;
  }
  .booknow:hover { background: var(--gold); }
</style>
</head>
<body>
<div class="wrap">

<h1>Europa-priser med EuroBonus</h1>
<p class="meta">
  <a href="/">← Fly-monitor</a> · <a href="/admin.html">Admin-versjon</a> · Sist oppdatert {{ generated }}
</p>

<p style="font-size:14px;">
  Pris og tilgjengelighet for Europa-destinasjoner med EuroBonus-poeng.
  De fleste ruter er <strong>15k pts Y / 35k pts J</strong> hver vei. Noen er billigere
  (intra-EU short-haul som München/Vilnius på <strong>10k/20k</strong>),
  noen er dyrere (Frankfurt på 47k/103k = unngå).
</p>

<div class="legend">
  <span>🟢 Bra deal</span>
  <span>🟡 Normalt</span>
  <span>🔴 Unngå</span>
</div>

{% for origin, rows in by_origin %}
<h2>Fra {{ origin }}</h2>
<table>
<thead>
<tr>
  <th>Destinasjon</th>
  <th class="num">Datoer</th>
  <th class="num">J 2+</th>
  <th class="num">Y</th>
  <th class="num">Y pts</th>
  <th class="num">J pts</th>
  <th>Tidligst</th>
  <th>Book</th>
</tr>
</thead>
<tbody>
{% for r in rows %}
<tr>
  <td class="dest">{{ r.code }} — {{ r.name }}</td>
  <td class="num">{{ r.total }}</td>
  <td class="num">{{ r.j_2plus }}</td>
  <td class="num">{{ r.y_avail }}</td>
  <td class="num cost {{ 'cheap' if r.y_cost and r.y_cost <= 12000 else ('expensive' if r.y_cost > 25000 else '') }}">
    {{ fmt(r.y_cost) }}
  </td>
  <td class="num cost {{ 'cheap' if r.j_cost and r.j_cost <= 22000 else ('expensive' if r.j_cost > 50000 else '') }}">
    {{ fmt(r.j_cost) }}
  </td>
  <td class="dates">{{ r.j_first or r.y_first or '—' }}</td>
  <td><a class="booknow" href="{{ sas(origin, r.code) }}" target="_blank">SAS</a></td>
</tr>
{% endfor %}
</tbody>
</table>
{% endfor %}

<p class="meta" style="margin-top:36px;">
  Eco = 15k pts hver vei = 30k RT × 2 pax = 60k. Med Companion Ticket: ~30k pts for 2 pax RT.<br>
  Business = 35k pts hver vei = 70k RT × 2 pax = 140k. Med CT: ~70k pts.<br>
  Mamma har 180k pts → mange Europa-turer mulig.
</p>

</div>
</body>
</html>
""")


def _sas_link(origin, dest):
    return "https://www.flysas.com/en/book/flights/?" + urlencode({
        "bookingFlow": "BONUS", "from": origin, "to": dest,
        "adt": 2, "chd": 0, "inf": 0,
    })


def _fmt(n):
    if not n:
        return "—"
    return f"{n:,}".replace(",", " ")


def render(data: dict | None = None) -> str:
    if data is None:
        data = fetch_all()
        # cache
        cache = config.CACHE_DIR / "europa.json"
        cache.write_text(json.dumps(data, indent=2))

    name_map = dict(EUROPA_DESTINATIONS)
    by_origin = []
    for origin in ORIGINS:
        rows = []
        for dest, name in EUROPA_DESTINATIONS:
            stats = data.get(origin, {}).get(dest)
            if stats:
                rows.append({"code": dest, "name": name, **stats})
        # sorter på Y-pris
        rows.sort(key=lambda x: x["y_cost"] or 999999)
        if rows:
            by_origin.append((origin, rows))

    html = TEMPLATE.render(
        by_origin=by_origin,
        sas=_sas_link, fmt=_fmt,
        generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )
    out = config.OUTPUT_DIR / "europa.html"
    out.write_text(html)
    log.info("Europa-side skrevet til %s", out)
    return str(out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(render())
