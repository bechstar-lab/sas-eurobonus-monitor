"""Dashboard.html — destinasjons-orientert med trip-par + manuelle quick checks."""
from __future__ import annotations

import json
import logging
from datetime import datetime, date
from urllib.parse import urlencode

from jinja2 import Template

import config
from alerts import recent_alerts
from links import all_routes_links
from hotels import for_trip as hotels_for_trip

log = logging.getLogger("dashboard")


def _sas_link(origin: str, dest: str, out_date: str, ret_date: str | None = None) -> str:
    p = {"bookingFlow": "BONUS", "from": origin, "to": dest,
         "outDate": out_date, "adt": 2, "chd": 0, "inf": 0}
    if ret_date:
        p["retDate"] = ret_date
    return "https://www.flysas.com/en/book/flights/?" + urlencode(p)


def _af_link(origin: str, dest: str) -> str:
    return "https://awardfares.com/search?" + urlencode({
        "origin": f"{origin}.", "destination": f"{dest}.",
        "cabin": "C", "program": "EuroBonus",
    })


def _fmt_pts(n: int | None) -> str:
    if not n:
        return "—"
    return f"{n:,}".replace(",", " ")


TEMPLATE = Template("""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>SAS EuroBonus Monitor</title>
<style>
  :root {
    --bg: #FAF7F2; --ink: #5C4B3A; --muted: #8a7a66;
    --line: #e5ddd0; --card: #ffffff;
    --gold: #b58a4e; --green: #4a6f4a; --red: #a3565b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 32px 24px; background: var(--bg); color: var(--ink);
    font: 16px/1.5 Georgia, "EB Garamond", Garamond, serif;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  h1 { font-weight: 600; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }
  .meta { color: var(--muted); font-size: 14px; margin: 0 0 28px; }
  h2 {
    font-weight: 600; font-size: 14px; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--muted);
    margin: 36px 0 14px; border-bottom: 1px solid var(--line); padding-bottom: 6px;
  }
  h3 { font-weight: 600; font-size: 18px; margin: 24px 0 8px; }

  .stats { display: flex; flex-wrap: wrap; gap: 28px; margin-bottom: 12px; }
  .stat .num { font-size: 26px; font-weight: 600; display: block; }
  .stat .lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }

  .destgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px,1fr)); gap: 14px; margin-top: 8px; }
  .destcard {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 16px 18px;
  }
  .destcard h4 {
    font-weight: 600; font-size: 17px; margin: 0 0 4px; letter-spacing: -0.01em;
  }
  .destcard .sub { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
  .destcard .count {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    background: var(--bg); font-size: 12px; color: var(--muted); border: 1px solid var(--line);
  }
  .destcard .count.has { background: #f1ead8; color: var(--gold); border-color: var(--gold); }

  .trip {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 18px; margin: 10px 0;
  }
  .trip .head { display: flex; justify-content: space-between; gap: 16px; align-items: baseline; flex-wrap: wrap; }
  .trip .route { font-weight: 600; font-size: 18px; }
  .trip .route .arrow { color: var(--muted); margin: 0 6px; }
  .trip .pts { font-weight: 600; font-size: 18px; color: var(--gold); }
  .trip .legs { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; font-size: 14px; }
  .leg { padding: 10px 12px; background: var(--bg); border-radius: 6px; }
  .leg .lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
  .leg .when { font-weight: 600; }
  .leg .meta { font-size: 12px; color: var(--muted); margin-top: 2px; }

  .pill {
    display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px;
    background: var(--bg); border: 1px solid var(--line); color: var(--muted);
    font-family: -apple-system, sans-serif; margin-right: 4px;
  }
  .pill.business { background: #f1ead8; color: var(--gold); border-color: var(--gold); }
  .pill.premium_economy { background: #e8eee4; color: var(--green); border-color: var(--green); }
  .pill.direct { background: #e8eee4; color: var(--green); border-color: var(--green); }
  .pill.connect { background: #f5e8e8; color: var(--red); border-color: var(--red); }
  .pill.risk-medium { background: #f7eedb; color: #8a6520; border-color: #d2a04e; }
  .pill.risk-high { background: #f5e8e8; color: var(--red); border-color: var(--red); }
  .warning {
    background: #fff8e1; border: 1px solid #d2a04e; color: #6d5223;
    border-radius: 8px; padding: 12px 16px; margin: 16px 0; font-size: 14px;
  }
  .booknow {
    display: inline-block; background: var(--ink); color: var(--bg);
    padding: 10px 22px; border-radius: 6px; text-decoration: none;
    font: 600 14px -apple-system, sans-serif; margin-top: 12px;
  }
  .booknow:hover { background: var(--gold); }
  .segments { margin-top: 12px; font-size: 12px; font-family: -apple-system, sans-serif; }
  .seg { display: flex; gap: 10px; padding: 6px 0; border-top: 1px dashed var(--line); }
  .seg:first-child { border-top: none; }
  .seg .time { font-variant-numeric: tabular-nums; color: var(--muted); min-width: 90px; }
  .seg .route { font-weight: 600; min-width: 90px; }
  .seg .meta { color: var(--muted); flex: 1; }
  .seg.business { background: rgba(181,138,78,0.06); }
  .layover {
    padding: 4px 10px; color: var(--muted); font-style: italic; font-size: 11px;
    background: var(--bg); border-radius: 4px; margin: 2px 0;
  }
  .layover.short { color: var(--red); }
  .layover.long { color: #6d5223; }
  .journey-summary {
    margin-top: 8px; font-size: 13px; color: var(--muted);
    font-family: -apple-system, sans-serif;
  }
  .hotels {
    margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--line);
    font-size: 13px; font-family: -apple-system, sans-serif;
  }
  .hotels strong { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
  .hotels a { color: var(--ink); margin-right: 14px; }

  .filterbar {
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 12px 16px; margin: 18px 0; display: flex; gap: 18px; align-items: center; flex-wrap: wrap;
    font-family: -apple-system, sans-serif; font-size: 13px;
  }
  .filterbar label { color: var(--muted); margin-right: 6px; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
  .filterbar select, .filterbar button {
    background: var(--bg); border: 1px solid var(--line); border-radius: 4px;
    padding: 4px 10px; font: inherit; cursor: pointer;
  }
  .filterbar button.clear { color: var(--muted); }
  .trip.skipped {
    opacity: 0.35; background: #f5f1ea;
  }
  .trip.skipped .booknow { display: none; }
  .skip-btn {
    background: transparent; border: 1px solid var(--line); border-radius: 4px;
    padding: 4px 10px; cursor: pointer; color: var(--muted);
    font: 11px -apple-system, sans-serif; margin-left: 12px;
  }
  .skip-btn:hover { background: #f5e8e8; color: var(--red); border-color: var(--red); }
  .trip.skipped .skip-btn::before { content: "↺ "; }
  .trip.skipped .skip-btn { color: var(--green); border-color: var(--green); }

  .book-btn {
    background: transparent; border: 1px solid var(--gold); color: var(--gold);
    border-radius: 4px; padding: 4px 10px; cursor: pointer;
    font: 11px -apple-system, sans-serif; margin-left: 8px;
  }
  .book-btn:hover { background: var(--gold); color: white; }
  .trip.booked { background: #fff8e8; border-color: var(--gold); }
  .trip.booked .book-btn { background: var(--gold); color: white; }
  .trip.booked .book-btn::before { content: "✓ "; }

  .feedback {
    margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--line);
    font-family: -apple-system, sans-serif;
  }
  .feedback textarea {
    width: 100%; border: 1px solid var(--line); border-radius: 4px;
    padding: 6px 10px; font: 13px -apple-system, sans-serif;
    resize: vertical; min-height: 32px; background: var(--bg);
  }
  .feedback .rate { display: inline-flex; gap: 4px; margin-right: 12px; }
  .feedback .rate button {
    background: transparent; border: 1px solid var(--line); border-radius: 999px;
    width: 28px; height: 28px; cursor: pointer; font-size: 14px;
  }
  .feedback .rate button.active.up { background: #e8eee4; border-color: var(--green); color: var(--green); }
  .feedback .rate button.active.down { background: #f5e8e8; border-color: var(--red); color: var(--red); }
  .feedback .saved { font-size: 11px; color: var(--green); margin-left: 8px; }

  .rules-card {
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 14px 18px; margin-bottom: 18px; font-size: 13px;
    font-family: -apple-system, sans-serif;
  }
  .rules-card h3 {
    font: 600 11px -apple-system, sans-serif; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 8px;
  }
  .rules-card .row { display: flex; gap: 18px; flex-wrap: wrap; padding: 4px 0; }
  .rules-card .row span { color: var(--muted); }
  .rules-card .row strong { color: var(--ink); font-weight: 600; }

  .daterange { display: flex; gap: 8px; align-items: center; }
  .daterange input { font: inherit; padding: 4px 8px; border: 1px solid var(--line); border-radius: 4px; }

  .links { margin-top: 10px; font-size: 13px; font-family: -apple-system, sans-serif; }
  .links a { color: var(--ink); margin-right: 14px; text-decoration: underline; text-decoration-color: var(--line); }
  .links a:hover { text-decoration-color: var(--ink); }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
  .quick td { font-family: -apple-system, sans-serif; }
  .quick td a { color: var(--ink); }

  .empty { color: var(--muted); font-style: italic; padding: 12px 0; }
  details summary { cursor: pointer; padding: 8px 0; color: var(--muted); font-size: 13px; }
  .toolbar {
    display: flex; gap: 12px; align-items: center; margin-bottom: 18px;
    font-family: -apple-system, sans-serif;
  }
  button.refresh {
    background: var(--ink); color: var(--bg); border: none; border-radius: 6px;
    padding: 8px 18px; font: 600 14px -apple-system, sans-serif; cursor: pointer;
  }
  button.refresh:hover { background: var(--gold); }
  button.refresh:disabled { opacity: 0.5; cursor: wait; }
  .freshness { font-size: 12px; color: var(--muted); }
  .freshness.stale { color: var(--red); }
  .freshness.fresh { color: var(--green); }
</style>
<script>
  // Detect om vi kjører lokalt (Flask) eller på Pages (statisk)
  const isStatic = location.host.includes('github.io') || location.protocol === 'file:';

  async function refresh(btn) {
    if (isStatic) {
      btn.disabled = true;
      btn.textContent = "Auto: hver 6. time";
      btn.style.opacity = "0.6";
      btn.title = "Statisk hosting — refresh skjer via GitHub Actions";
      return;
    }
    btn.disabled = true;
    btn.textContent = "Sjekker…";
    try {
      const r = await fetch('/refresh', {method:'POST'});
      const j = await r.json();
      if (j.running) {
        btn.textContent = "Kjører allerede…";
      }
      const start = Date.now();
      while (true) {
        await new Promise(r => setTimeout(r, 1500));
        const s = await (await fetch('/status')).json();
        if (!s.running && s.finished) {
          btn.textContent = "Ferdig — laster…";
          break;
        }
        const sec = Math.round((Date.now() - start)/1000);
        btn.textContent = `Kjører… ${sec}s`;
      }
      location.reload();
    } catch(e) {
      btn.textContent = "Feilet — prøv igjen";
      btn.disabled = false;
    }
  }
  function ageOf(iso) {
    if (!iso) return null;
    const ms = Date.now() - new Date(iso).getTime();
    const m = Math.round(ms / 60000);
    if (m < 60) return `${m}m`;
    const h = Math.round(m / 60);
    if (h < 48) return `${h}t`;
    return `${Math.round(h/24)}d`;
  }
  // Skip / book / comment state via localStorage
  const lsKey = (k, id) => `${k}:${id}`;
  function getLs(k, id) { return localStorage.getItem(lsKey(k, id)); }
  function setLs(k, id, v) {
    if (v === null || v === '') localStorage.removeItem(lsKey(k, id));
    else localStorage.setItem(lsKey(k, id), v);
  }

  function isSkipped(tripId) { return getLs('skip', tripId) === '1'; }
  function toggleSkip(tripId, btn) {
    const trip = btn.closest('.trip');
    if (isSkipped(tripId)) {
      setLs('skip', tripId, null);
      trip.classList.remove('skipped');
      btn.textContent = 'Ikke aktuell';
    } else {
      setLs('skip', tripId, '1');
      trip.classList.add('skipped');
      btn.textContent = 'Vis igjen';
    }
    applyFilters();
  }

  function isBooked(tripId) { return getLs('booked', tripId) === '1'; }
  function toggleBook(tripId, btn) {
    const trip = btn.closest('.trip');
    if (isBooked(tripId)) {
      setLs('booked', tripId, null);
      trip.classList.remove('booked');
      btn.textContent = 'Marker som booket';
      // skjul hotell
      const h = trip.querySelector('.hotels'); if (h) h.style.display = 'none';
    } else {
      setLs('booked', tripId, '1');
      // lagre trip-payload for hotells-siden
      const payload = {
        id: tripId,
        dest: trip.dataset.dest,
        origin: trip.dataset.origin,
        dest_airport: trip.querySelector('.route').textContent.match(/[A-Z]{3}/g)[1],
        out_date: trip.dataset.outdate,
        ret_date: trip.dataset.retdate || '',
        cabin: trip.dataset.cabin,
      };
      setLs('booked_data', tripId, JSON.stringify(payload));
      trip.classList.add('booked');
      btn.textContent = 'Booket';
      const m = trip.querySelector('.trip-booked-msg'); if (m) m.style.display = 'inline';
    }
    applyFilters();
  }

  function rate(tripId, value, container) {
    const current = getLs('rate', tripId);
    const newVal = current === value ? null : value;
    setLs('rate', tripId, newVal);
    container.querySelectorAll('button').forEach(b => {
      b.classList.toggle('active', b.dataset.value === newVal);
      b.classList.toggle('up', b.dataset.value === 'up');
      b.classList.toggle('down', b.dataset.value === 'down');
    });
  }

  function saveComment(tripId, ta) {
    setLs('comment', tripId, ta.value);
    const saved = ta.parentElement.querySelector('.saved');
    if (saved) {
      saved.textContent = '✓ lagret';
      setTimeout(() => saved.textContent = '', 1500);
    }
  }

  // Filter state
  function applyFilters() {
    const dest = document.getElementById('f-dest').value;
    const origin = document.getElementById('f-origin').value;
    const cabin = document.getElementById('f-cabin').value;
    const direct = document.getElementById('f-direct').checked;
    const hideSkip = document.getElementById('f-hideskip').checked;
    const dateFrom = document.getElementById('f-date-from').value;
    const dateTo = document.getElementById('f-date-to').value;

    let visible = 0;
    document.querySelectorAll('.trip').forEach(t => {
      let show = true;
      if (dest && t.dataset.dest !== dest) show = false;
      if (origin && t.dataset.origin !== origin) show = false;
      if (cabin && t.dataset.cabin !== cabin) show = false;
      if (direct && t.dataset.direct !== '1') show = false;
      if (hideSkip && t.classList.contains('skipped')) show = false;
      const od = t.dataset.outdate;
      if (dateFrom && od && od < dateFrom) show = false;
      if (dateTo && od && od > dateTo) show = false;
      t.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    const counter = document.getElementById('visible-count');
    if (counter) counter.textContent = visible;
  }

  function clearFilters() {
    ['f-dest','f-origin','f-cabin','f-date-from','f-date-to'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('f-direct').checked = false;
    applyFilters();
  }

  document.addEventListener('DOMContentLoaded', () => {
    // På statisk hosting: bytt knapp-tekst med info istedenfor å invitere til feil
    if (isStatic) {
      const btn = document.querySelector('button.refresh');
      if (btn) {
        btn.textContent = 'Oppdateres auto hver 6. time';
        btn.disabled = true;
        btn.style.opacity = "0.6";
        btn.style.cursor = "default";
      }
    }
    // freshness pills
    document.querySelectorAll('[data-iso]').forEach(el => {
      const a = ageOf(el.dataset.iso);
      if (!a) return;
      const ms = Date.now() - new Date(el.dataset.iso).getTime();
      const h = ms / 3600000;
      el.textContent = `${a} gml`;
      el.classList.add(h < 12 ? 'fresh' : (h < 36 ? '' : 'stale'));
    });
    // restore skip / book / comment / rate-state
    document.querySelectorAll('.trip[data-trip-id]').forEach(t => {
      const id = t.dataset.tripId;
      if (isSkipped(id)) {
        t.classList.add('skipped');
        const btn = t.querySelector('.skip-btn');
        if (btn) btn.textContent = 'Vis igjen';
      }
      if (isBooked(id)) {
        t.classList.add('booked');
        const btn = t.querySelector('.book-btn');
        if (btn) btn.textContent = 'Booket';
        const m = t.querySelector('.trip-booked-msg'); if (m) m.style.display = 'inline';
      }
      const c = getLs('comment', id);
      if (c) {
        const ta = t.querySelector('textarea'); if (ta) ta.value = c;
      }
      const r = getLs('rate', id);
      if (r) {
        const btn = t.querySelector(`.rate button[data-value="${r}"]`);
        if (btn) {
          btn.classList.add('active');
          btn.classList.add(r);
        }
      }
    });
    applyFilters();
  });
</script>
</head>
<body>
<div class="wrap">

<h1>SAS EuroBonus Monitor</h1>
<div class="toolbar">
  <button class="refresh" onclick="refresh(this)">Sjekk på nytt</button>
  <span class="freshness" data-iso="{{ last_run.finished }}">{{ last_run.finished or '—' }}</span>
</div>
<p class="meta">
  Sist sjekket {{ last_run.finished or '—' }} ·
  seats.aero {{ 'API ✓' if last_run.seats_aero_key_present else 'mangler key' }} ·
  CT-deadline: {{ ct_deadline }}
</p>

<div class="stats">
  <div class="stat"><span class="num">{{ total_flights }}</span><span class="lbl">flights tilgjengelig</span></div>
  <div class="stat"><span class="num">{{ total_pairs }}</span><span class="lbl">trip-par funnet</span></div>
  <div class="stat"><span class="num">{{ destinations|length }}</span><span class="lbl">destinasjoner</span></div>
  <div class="stat"><span class="num">{{ alerts|length }}</span><span class="lbl">siste alerts</span></div>
</div>

<div class="warning">
  <strong>⚠️ Phantom availability:</strong> seats.aero cacher data 4-24t. Et "tilbud" her kan være borte når du går til SAS.
  <strong>Klikk alltid Book på SAS først</strong> for å verifisere før du blir glad. Tilbud markert
  <span class="pill risk-medium">stale</span> eller <span class="pill risk-high">gammel</span> har høyere phantom-risiko.
</div>

<div class="rules-card">
  <h3>Aktive regler</h3>
  <div class="row">
    <span><strong>Min seter:</strong> {{ default_min_seats }}</span>
    <span><strong>Reisevindu:</strong> {{ window_start }} → {{ window_end }}</span>
    <span><strong>CT-deadline:</strong> {{ ct_deadline }}</span>
    <span><strong>Klasser:</strong> Business (prio) + Premium Eco</span>
  </div>
  <div class="row" style="margin-top:6px;">
    <span style="color:var(--muted);">Per destinasjon (rediger destinations.yaml):</span>
  </div>
  <div class="row" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
    {% for d in destinations %}
    <div style="border-left:2px solid var(--line);padding-left:10px;">
      <strong>{{ d.name }}</strong> — {{ d.airports|join('/') }}<br>
      <span>{{ d.trip_min_days }}-{{ d.trip_max_days }} dgr · fra {{ d.origin_priority|join('/') }}</span>
      {% if d.requires_connection %}<br><span style="color:var(--red);">krever connection</span>{% endif %}
    </div>
    {% endfor %}
  </div>
</div>

<div class="filterbar">
  <span><label>Filter:</label></span>
  <span>
    <label>Destinasjon</label>
    <select id="f-dest" onchange="applyFilters()">
      <option value="">Alle</option>
      {% for d in destinations %}<option>{{ d.name }}</option>{% endfor %}
    </select>
  </span>
  <span>
    <label>Avreise</label>
    <select id="f-origin" onchange="applyFilters()">
      <option value="">Alle</option>
      <option>OSL</option><option>CPH</option><option>ARN</option><option>GOT</option>
    </select>
  </span>
  <span>
    <label>Klasse</label>
    <select id="f-cabin" onchange="applyFilters()">
      <option value="">Alle</option>
      <option value="business">Business</option>
      <option value="premium_economy">Premium Eco</option>
    </select>
  </span>
  <span class="daterange">
    <label>Dato (ut)</label>
    <input id="f-date-from" type="date" onchange="applyFilters()">
    <span style="color:var(--muted);">→</span>
    <input id="f-date-to" type="date" onchange="applyFilters()">
  </span>
  <span><label><input id="f-direct" type="checkbox" onchange="applyFilters()"> kun direkte</label></span>
  <span><label><input id="f-hideskip" type="checkbox" checked onchange="applyFilters()"> skjul skippet</label></span>
  <button class="clear" onclick="clearFilters()">Nullstill</button>
  <span style="color:var(--muted);margin-left:auto;">Viser <strong id="visible-count">0</strong> trips</span>
</div>

<h2>Topp deals (verifisert)</h2>
{% if top_deals %}
{% for t in top_deals %}
{% set both_direct = (t.out.stops == 'Direct' and t.ret.stops == 'Direct') %}
{% set trip_id = t.destination ~ '|' ~ t.out.origin ~ t.out.destination ~ '|' ~ t.out.date ~ '|' ~ t.ret.date ~ '|' ~ t.cabin %}
<div class="trip"
     data-trip-id="{{ trip_id }}"
     data-dest="{{ t.destination }}"
     data-origin="{{ t.out.origin }}"
     data-cabin="{{ t.cabin }}"
     data-direct="{{ '1' if both_direct else '0' }}"
     data-outdate="{{ t.out.date }}"
     data-retdate="{{ t.ret.date }}">
  <div class="head">
    <div class="route">
      {{ t.origin }}<span class="arrow">→</span>{{ t.dest_airport }}<span class="arrow">→</span>{{ t.origin }}
      <span class="pill {{ t.cabin }}">{{ 'Business' if t.cabin == 'business' else 'Premium Eco' }}</span>
      {% if both_direct %}<span class="pill direct">Begge direkte</span>{% endif %}
      {% if t.phantom_risk == 'medium' %}<span class="pill risk-medium">stale {{ t.max_age_hours }}t</span>{% endif %}
      {% if t.phantom_risk == 'high' %}<span class="pill risk-high">gammel {{ t.max_age_hours }}t</span>{% endif %}
    </div>
    <div class="pts">{{ fmt(t.total_pts) }} pts · {{ t.trip_days }} dgr · {{ t.destination }}</div>
  </div>
  <div class="legs">
    {% for leg_name, leg, det in [('Ut', t.out, t.out_details), ('Hjem', t.ret, t.ret_details)] %}
    <div class="leg">
      <div class="lbl">{{ leg_name }}</div>
      <div class="when">{{ leg.date }} · {{ leg.origin }} → {{ leg.destination }}</div>
      <div class="meta">{{ leg.seats }} seter · {{ fmt(leg.mileage_cost) }} pts · {{ leg.stops or '?' }} · {{ leg.airline or '' }}
        {% if leg.raw and leg.raw.last_seen %}<span class="freshness" data-iso="{{ leg.raw.last_seen }}"></span>{% endif %}
      </div>
      {% if det and det.verified %}
      <div class="journey-summary">
        Total {{ (det.total_journey_min // 60) }}t {{ '%02d' % (det.total_journey_min % 60) }}m
        ({{ (det.total_flight_min // 60) }}t {{ '%02d' % (det.total_flight_min % 60) }}m fly,
         {{ (det.total_layover_min // 60) }}t {{ '%02d' % (det.total_layover_min % 60) }}m vente)
        {% if not det.cabin_match %}· <span style="color:var(--red);">long-haul = {{ det.long_haul_cabin }} (ikke business!)</span>{% endif %}
      </div>
      <div class="segments">
        {% for seg in det.segments %}
        <div class="seg {{ 'business' if seg.cabin == 'business' else '' }}">
          <span class="time">{{ seg.departs[11:16] }}–{{ seg.arrives[11:16] }}</span>
          <span class="route">{{ seg.from }}→{{ seg.to }}</span>
          <span class="meta">{{ seg.flight_no }} · {{ seg.aircraft or '?' }} · {{ (seg.duration_min // 60) }}t{{ '%02d' % (seg.duration_min % 60) }}m · {{ seg.cabin or '?' }}</span>
        </div>
        {% if not loop.last %}
          {% set lo = det.layovers[loop.index0] if det.layovers and loop.index0 < det.layovers|length else none %}
          {% if lo %}
          <div class="layover {{ 'short' if lo.minutes < 90 else ('long' if lo.minutes > 240 else '') }}">
            ↳ {{ lo.airport }} · {{ (lo.minutes // 60) }}t {{ '%02d' % (lo.minutes % 60) }}m vente
          </div>
          {% endif %}
        {% endif %}
        {% endfor %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  <a class="booknow" href="{{ sas(t.out.origin, t.out.destination, t.out.date, t.ret.date) }}" target="_blank">
    Book fly på SAS →
  </a>
  <span style="margin-left:14px;font-family:-apple-system,sans-serif;font-size:13px;">
    <a href="{{ af(t.out.origin, t.out.destination) }}" target="_blank" style="color:var(--muted);">AwardFares</a>
  </span>
  <button class="book-btn" onclick="toggleBook('{{ trip_id }}', this)">Marker som booket</button>
  <button class="skip-btn" onclick="toggleSkip('{{ trip_id }}', this)">Ikke aktuell</button>
  <span class="trip-booked-msg" style="display:none;margin-left:10px;font-size:13px;color:var(--gold);font-family:-apple-system,sans-serif;">
    ✓ Sjekk <a href="/hotels">Hotell-siden</a> for neste steg
  </span>

  <div class="feedback">
    <span class="rate">
      <button data-value="up" onclick="rate('{{ trip_id }}','up',this.parentElement)" title="Bra forslag">👍</button>
      <button data-value="down" onclick="rate('{{ trip_id }}','down',this.parentElement)" title="Dårlig forslag">👎</button>
    </span>
    <textarea placeholder="Notat / tilbakemelding på dette forslaget…"
              onblur="saveComment('{{ trip_id }}', this)"></textarea>
    <span class="saved"></span>
  </div>

  {% if t.notes %}<div style="font-size:12px;color:var(--muted);margin-top:6px;">{{ t.notes|join(' · ') }}</div>{% endif %}
</div>
{% endfor %}
{% else %}
<p class="empty">Ingen trip-par funnet i siste sjekk.</p>
{% endif %}

<h2>Per destinasjon</h2>
<div class="destgrid">
{% for dest in destinations %}
  {% set pairs = trip_pairs.get(dest.name, []) %}
  <div class="destcard">
    <h4>{{ dest.name }}
      <span class="count {{ 'has' if pairs else '' }}">{{ pairs|length }} par</span>
    </h4>
    <div class="sub">
      Fly: {{ dest.airports|join(', ') }} ·
      Fra: {{ dest.origin_priority|join(' / ') }} ·
      {{ dest.trip_min_days }}-{{ dest.trip_max_days }} dgr
      {% if dest.requires_connection %}<br><em>Krever connection — sjekk manuelt</em>{% endif %}
    </div>
    {% if dest.notes %}<div class="sub" style="font-style:italic;">{{ dest.notes }}</div>{% endif %}
    {% if pairs %}
      {% set best = pairs[0] %}
      <div style="margin-top:8px;font-size:13px;">
        Best: <strong>{{ best.out.date }} → {{ best.ret.date }}</strong>
        ({{ best.trip_days }} dgr, {{ fmt(best.total_pts) }} pts, {{ best.origin }})
      </div>
      {% if pairs|length > 1 %}
      <details>
        <summary>Vis alle {{ pairs|length }} par</summary>
        <table style="margin-top:6px;">
          <thead><tr><th>Ut</th><th>Hjem</th><th>Dgr</th><th>Fra</th><th>Klasse</th><th>Pts</th></tr></thead>
          <tbody>
          {% for p in pairs[:30] %}
            <tr>
              <td>{{ p.out.date }}</td>
              <td>{{ p.ret.date }}</td>
              <td>{{ p.trip_days }}</td>
              <td>{{ p.origin }}→{{ p.dest_airport }}</td>
              <td>{{ 'J' if p.cabin == 'business' else 'W' }}</td>
              <td>{{ fmt(p.total_pts) }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </details>
      {% endif %}
    {% else %}
      <div class="sub" style="margin-top:8px;">Ingen par funnet.</div>
    {% endif %}
  </div>
{% endfor %}
</div>

<h2>Quick checks (manuelt)</h2>
<p class="meta">Klikk for å sjekke hos SAS / AwardFares / partnere. Datoer = midt i søkevinduet.</p>
<table class="quick">
<thead>
  <tr><th>Rute</th><th>SAS</th><th>AwardFares</th><th>Flying Blue</th><th>KLM</th><th>Delta</th><th>Google</th></tr>
</thead>
<tbody>
{% for r in route_links %}
  <tr>
    <td><strong>{{ r.origin }}→{{ r.destination }}</strong></td>
    <td><a href="{{ r.sas }}" target="_blank">SAS</a></td>
    <td><a href="{{ r.awardfares }}" target="_blank">AF</a></td>
    <td><a href="{{ r.flying_blue }}" target="_blank">FB</a></td>
    <td><a href="{{ r.klm }}" target="_blank">KL</a></td>
    <td><a href="{{ r.delta }}" target="_blank">DL</a></td>
    <td><a href="{{ r.google_flights }}" target="_blank">GF</a></td>
  </tr>
{% endfor %}
</tbody>
</table>

<h2>Siste 10 alerts</h2>
{% if alerts %}
<table>
<thead><tr><th>Tid (UTC)</th><th>Subject</th><th>Sammendrag</th></tr></thead>
<tbody>
{% for a in alerts %}
  <tr><td>{{ a.sent_at }}</td><td>{{ a.subject }}</td><td>{{ a.summary }}</td></tr>
{% endfor %}
</tbody>
</table>
{% else %}
<p class="empty">Ingen alerts sendt ennå.</p>
{% endif %}

<p class="meta" style="margin-top:40px;">
  Generert {{ generated }} · {{ last_run.routes_checked|length }} ruter sjekket
</p>
</div>
</body>
</html>
""")


def render(last_run: dict | None = None) -> str:
    if last_run is None:
        if config.LAST_RUN_PATH.exists():
            last_run = json.loads(config.LAST_RUN_PATH.read_text())
        else:
            last_run = {"finished": None, "total": 0, "routes_checked": [],
                        "matching": [], "trip_pairs": {}, "top_deals": [],
                        "seats_aero_key_present": False}

    trip_pairs = last_run.get("trip_pairs", {})
    total_pairs = sum(len(v) for v in trip_pairs.values())
    ct_deadline = config.DESTINATIONS[0].booking_deadline if config.DESTINATIONS else "?"

    html = TEMPLATE.render(
        last_run=last_run,
        total_flights=last_run.get("total", 0),
        total_pairs=total_pairs,
        destinations=config.DESTINATIONS,
        trip_pairs=trip_pairs,
        top_deals=last_run.get("top_deals", []),
        alerts=recent_alerts(10),
        ct_deadline=ct_deadline,
        window_start=config.START_DATE,
        window_end=config.END_DATE,
        default_min_seats=config.MIN_SEATS,
        generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        route_links=all_routes_links(),
        sas=_sas_link, af=_af_link, fmt=_fmt_pts,
        hotels=hotels_for_trip,
    )
    config.DASHBOARD_PATH.write_text(html)
    log.info("Dashboard skrevet til %s", config.DASHBOARD_PATH)
    return str(config.DASHBOARD_PATH)


if __name__ == "__main__":
    print(render())
