"""
Forenklet visningsversjon for deling (mamma).
Read-only: ingen filter, skip, book, kommentar — bare det som teller.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from jinja2 import Template

import config
from urllib.parse import urlencode

log = logging.getLogger("dashboard_share")


def _sas_link(o, d, out, ret=None):
    p = {"bookingFlow": "BONUS", "from": o, "to": d,
         "outDate": out, "adt": 2, "chd": 0, "inf": 0}
    if ret:
        p["retDate"] = ret
    return "https://www.flysas.com/en/book/flights/?" + urlencode(p)


def _fmt(n):
    if not n:
        return "—"
    return f"{n:,}".replace(",", " ")


TEMPLATE = Template("""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>SAS Award-deals</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #FAF7F2; --ink: #5C4B3A; --muted: #8a7a66;
    --line: #e5ddd0; --card: #ffffff; --gold: #b58a4e;
    --green: #4a6f4a; --red: #a3565b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px; background: var(--bg); color: var(--ink);
    font: 16px/1.55 Georgia, "EB Garamond", Garamond, serif;
  }
  .wrap { max-width: 760px; margin: 0 auto; }
  h1 {
    font-weight: 600; font-size: 26px; margin: 0 0 4px;
    letter-spacing: -0.01em;
  }
  .meta { color: var(--muted); font-size: 14px; margin: 0 0 28px; }
  .meta a { color: var(--ink); }

  .group {
    margin-top: 36px;
  }
  .group h2 {
    font-weight: 600; font-size: 14px; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--muted);
    margin: 0 0 14px; border-bottom: 1px solid var(--line); padding-bottom: 6px;
  }

  .trip {
    background: var(--card); border: 1px solid var(--line);
    border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
  }
  .trip .head { display: flex; justify-content: space-between; gap: 14px; align-items: baseline; flex-wrap: wrap; }
  .trip .route { font-weight: 600; font-size: 18px; }
  .trip .route .arrow { color: var(--muted); margin: 0 5px; font-weight: 400; }
  .trip .pts {
    font-weight: 600; font-size: 17px; color: var(--gold);
  }
  .trip .summary {
    margin: 8px 0 0; color: var(--muted); font-size: 14px;
    font-family: -apple-system, sans-serif;
  }
  .trip .summary strong { color: var(--ink); font-weight: 600; }

  .legs {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
    margin-top: 12px;
  }
  @media (max-width: 600px) {
    .legs { grid-template-columns: 1fr; }
  }
  .leg {
    background: var(--bg); border-radius: 6px; padding: 10px 12px;
    font-family: -apple-system, sans-serif; font-size: 13px;
  }
  .leg .lbl {
    font-size: 10px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;
  }
  .leg .when { font-weight: 600; font-size: 14px; }
  .leg .stops { color: var(--muted); margin-top: 4px; font-size: 12px; }

  .pill {
    display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px;
    background: var(--bg); border: 1px solid var(--line); color: var(--muted);
    font-family: -apple-system, sans-serif; margin-left: 4px;
  }
  .pill.business { background: #f1ead8; color: var(--gold); border-color: var(--gold); }
  .pill.premium_economy { background: #e8eee4; color: var(--green); border-color: var(--green); }
  .pill.economy { background: #f5f1ea; color: var(--muted); }
  .pill.direct { background: #e8eee4; color: var(--green); border-color: var(--green); }

  .booknow {
    display: inline-block; background: var(--ink); color: var(--bg);
    padding: 10px 22px; border-radius: 6px; text-decoration: none;
    font: 600 14px -apple-system, sans-serif; margin-top: 14px;
  }
  .booknow:hover { background: var(--gold); }

  .empty {
    background: var(--card); border: 1px dashed var(--line); border-radius: 10px;
    padding: 30px; text-align: center; color: var(--muted);
  }

  .warning {
    background: #fff8e1; border: 1px solid #d2a04e; color: #6d5223;
    border-radius: 8px; padding: 10px 14px; margin: 0 0 22px; font-size: 13px;
    font-family: -apple-system, sans-serif;
  }
  .intro {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 18px 22px; margin-bottom: 24px;
  }
  .intro h3 {
    font: 600 14px -apple-system, sans-serif; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 10px;
  }
  .intro p { margin: 0 0 10px; font-size: 15px; }
  .intro p:last-child { margin-bottom: 0; }
  .intro strong { color: var(--gold); }

  .toc {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 20px; margin: 0 0 24px;
    font-family: -apple-system, sans-serif; font-size: 13px;
  }
  .toc strong {
    color: var(--muted); font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.06em; display: block; margin-bottom: 6px;
  }
  .toc a {
    display: inline-block; margin-right: 16px; padding: 4px 0;
    color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--line);
  }
  .toc a:hover { border-bottom-color: var(--ink); }
</style>
</head>
<body>
<div class="wrap">

<h1>SAS EuroBonus award-deals</h1>
<p class="meta">
  Sist oppdatert {{ last_run.finished or '—' }} · {{ trip_count }} aktuelle reiser ·
  <a href="europa.html">Europa-priser →</a> ·
  <a href="hotels.html">Hotell →</a>
</p>

<div class="intro">
  <h3>Hva er dette?</h3>
  <p>
    Jonas overvåker SAS Business-billetter (og noen Premium Eco / Economy) som kan bookes
    med EuroBonus-poeng. Listen oppdateres flere ganger om dagen og viser kun reiser
    som matcher våre kriterier (lokasjon, lengde, klasse).
  </p>
  <p>
    <strong>Ser du noe interessant?</strong> Klikk "Book på SAS" — det åpner SAS sin
    side med datoene ferdig fylt inn. Du logger inn med din EuroBonus-konto og fullfører.
  </p>
</div>

<div class="warning">
  <strong>💡 Tips — 24-timers gratis avbestilling:</strong> SAS lar deg avbestille
  bonusbilletter <strong>gratis innen 24 timer</strong> fra booking. Poeng + skatter
  refunderes. Det betyr du kan trygt booke med en gang du ser noe bra — og avbestille
  hvis du angrer eller noe er galt. Bekreft eventuell Companion-Ticket-håndtering med
  EuroBonus support på telefon ved tvil.
</div>

<div class="warning" style="background:#f5f1ea;border-color:var(--line);color:var(--muted);">
  <strong>Merk:</strong> data er cachet inntil 6 timer fra seats.aero — i sjeldne
  tilfeller er en deal allerede borte når du klikker. Hvis SAS ikke viser samme
  pris/dato, prøv en annen dato eller en annen rute fra listen under.
</div>

{% if groups %}
<div class="toc">
  <strong>Hopp til</strong>
  {% for name, ts in groups %}<a href="#{{ name|lower|replace(' ','-') }}">{{ name }} ({{ ts|length }})</a>{% endfor %}
</div>
{% endif %}

{% for group_name, trips in groups %}
{% if trips %}
<div class="group" id="{{ group_name|lower|replace(' ','-') }}">
  <h2>{{ group_name }} — {{ trips|length }} alternativer</h2>
  {% for t in trips %}
  <div class="trip">
    <div class="head">
      <div class="route">
        {{ t.origin }}<span class="arrow">→</span>{{ t.dest_airport }}<span class="arrow">→</span>{{ t.origin }}
        <span class="pill {{ t.cabin }}">{{ cabin_label(t.cabin) }}</span>
        {% if t.out.stops == 'Direct' and t.ret.stops == 'Direct' %}<span class="pill direct">begge direkte</span>{% endif %}
      </div>
      <div class="pts">{{ fmt(t.total_pts) }} pts · {{ t.trip_days }} dgr</div>
    </div>

    <div class="legs">
      <div class="leg">
        <div class="lbl">Ut</div>
        <div class="when">{{ t.out.date }}</div>
        <div class="stops">{{ t.out.origin }} → {{ t.out.destination }} · {{ t.out.stops or '?' }}
          {% if t.out_details and t.out_details.verified %}
            · {{ (t.out_details.total_journey_min // 60) }}t{{ '%02d'|format(t.out_details.total_journey_min % 60) }}m
          {% endif %}
        </div>
      </div>
      <div class="leg">
        <div class="lbl">Hjem</div>
        <div class="when">{{ t.ret.date }}</div>
        <div class="stops">{{ t.ret.origin }} → {{ t.ret.destination }} · {{ t.ret.stops or '?' }}
          {% if t.ret_details and t.ret_details.verified %}
            · {{ (t.ret_details.total_journey_min // 60) }}t{{ '%02d'|format(t.ret_details.total_journey_min % 60) }}m
          {% endif %}
        </div>
      </div>
    </div>

    <a class="booknow" href="{{ sas(t.out.origin, t.out.destination, t.out.date, t.ret.date) }}" target="_blank">
      Book på SAS →
    </a>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endfor %}

{% if trip_count == 0 %}
<div class="empty">Ingen aktuelle reiser funnet i siste sjekk.</div>
{% endif %}

{% if watching %}
<div class="group">
  <h2>🎯 Ønske-destinasjoner — venter på award-åpning</h2>
  <div style="background:#fff8e1;border:1px solid #d2a04e;border-radius:10px;padding:14px 18px;font-family:-apple-system,sans-serif;font-size:13px;color:#6d5223;">
    <p style="margin:0 0 10px;">
      Disse er <strong>høyt ønsket</strong> men har ingen award-tilgjengelighet nå.
      Monitoren sjekker hver 6. time — når SAS slipper sete, fanger vi det opp.
    </p>
    {% for w in watching %}
    <div style="padding:6px 0;border-top:1px dashed #d2a04e;margin-top:6px;">
      <strong style="font-size:14px;">{{ w.name }}</strong>
      <span> — {{ w.airports|join('/') }}, {{ w.trip_min }}-{{ w.trip_max }} dgr</span><br>
      <span style="font-style:italic;font-size:12px;">{{ w.notes }}</span>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

{% if empty_dests %}
<div class="group">
  <h2>Ikke noe akkurat nå</h2>
  <div style="background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;font-family:-apple-system,sans-serif;font-size:13px;">
    <p style="margin:0 0 12px;color:var(--muted);">
      Disse destinasjonene overvåkes også, men har ikke matchende reiser nå.
      Kan dukke opp neste sjekk (hver 6. time):
    </p>
    {% for d in empty_dests %}
    <div style="padding:6px 0;border-top:1px dashed var(--line);">
      <strong>{{ d.name }}</strong>
      <span style="color:var(--muted);"> — {{ d.airports|join('/') }}, {{ d.trip_min }}-{{ d.trip_max }} dgr</span>
      <span style="color:var(--muted);font-style:italic;float:right;">{{ d.reason }}</span>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

<p class="meta" style="margin-top:40px;text-align:center;">
  Generert {{ generated }}
</p>

</div>
</body>
</html>
""")


def _cabin_label(c):
    return {"business": "Business", "premium_economy": "Premium Eco", "economy": "Economy"}.get(c, c)


def render(last_run: dict | None = None) -> str:
    if last_run is None:
        if config.LAST_RUN_PATH.exists():
            last_run = json.loads(config.LAST_RUN_PATH.read_text())
        else:
            last_run = {"finished": None, "trip_pairs": {}, "top_deals": []}

    # Grupper trips per destinasjon, vis topp 5 per gruppe
    trip_pairs = last_run.get("trip_pairs", {})
    groups = []
    empty_dests = []
    watching = []          # 🎯 ønske-destinasjoner som ikke har data ennå
    total = 0
    for dest in config.DESTINATIONS:
        pairs = trip_pairs.get(dest.name, [])
        is_wishlist = "🎯" in (dest.notes or "")

        if pairs:
            clean = [p for p in pairs if p.get("phantom_risk", "low") != "high"]
            top5 = clean[:5]
            if top5:
                groups.append((dest.name, top5))
                total += len(top5)
                continue
        # Ingen par funnet — kategoriser
        if is_wishlist:
            watching.append({
                "name": dest.name,
                "airports": dest.airports,
                "notes": dest.notes,
                "trip_min": dest.trip_min_days,
                "trip_max": dest.trip_max_days,
            })
            continue
        if dest.requires_connection:
            reason = "krever connection (sjekkes manuelt)"
        else:
            reason = "ingen matchende datoer i vinduet akkurat nå"
        empty_dests.append({
            "name": dest.name,
            "airports": dest.airports,
            "reason": reason,
            "trip_min": dest.trip_min_days,
            "trip_max": dest.trip_max_days,
        })

    html = TEMPLATE.render(
        last_run=last_run,
        groups=groups,
        empty_dests=empty_dests,
        watching=watching,
        trip_count=total,
        sas=_sas_link, fmt=_fmt, cabin_label=_cabin_label,
        generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )
    out = config.OUTPUT_DIR / "share.html"
    out.write_text(html)
    log.info("Share-dashboard skrevet til %s", out)
    return str(out)


if __name__ == "__main__":
    print(render())
