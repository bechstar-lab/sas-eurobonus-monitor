# SAS EuroBonus Award Monitor

Overvåker Business Class award-tilgjengelighet for to seter på samme avgang.
Primær kilde: **seats.aero** (Pro-key kreves). Fallback: **AwardFares public** via Playwright.

## Mål

- 200k pts (Jonas) + 300k pts (mamma), begge med Companion Ticket
- 120k pts RT Business for 2 pax (med CT) til USA / Asia
- Vindu: **2026-07-01 → 2027-02-28**

## Setup

```bash
cd "Projects/SAS EuroBonus Monitor"
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium      # bare hvis du bruker AwardFares-fallback
cp .env.example .env                       # fyll inn keys + SMTP
```

## Bruk

```bash
.venv/bin/python run.py check                    # én sjekk
.venv/bin/python run.py watch --interval 360     # daemon, hvert 6. time
.venv/bin/python run.py status                   # siste funn + config
.venv/bin/python run.py dashboard                # regenerer output/dashboard.html
.venv/bin/python test_smoke.py                   # kjør smoke-tester
```

## Filer

| Fil | Rolle |
|---|---|
| `config.py` | Ruter, vindu, env-lasting |
| `monitor.py` | seats.aero API + AwardFares-scraper + parser |
| `alerts.py` | SMTP-mail, SQLite dedup-cache, lenker |
| `dashboard.py` | Jinja2-rendret `output/dashboard.html` |
| `run.py` | CLI: check / watch / status / dashboard |
| `test_smoke.py` | Imports + parser + cache + lenker |
| `cache/seen.db` | Dedup + alert-logg |
| `cache/last_run.json` | Siste resultat |
| `logs/monitor.log` | Roterende logg |
| `output/dashboard.html` | Statisk dashboard |

## Hvordan det virker

1. `run.py check` → `monitor.run_check()`
2. **Hvis `SEATS_AERO_KEY` finnes** → kall `seats.aero` per rute (parameterisert request, parse `JBusinessAvailable` ≥ `MIN_SEATS`)
3. **Ellers/i tillegg** → Playwright headless mot `awardfares.com/programs/sas-eurobonus`, parse `#product-flight-list .result`, filtrer på `ORIGIN_AIRPORTS` + `TARGET_DESTINATIONS`
4. `alerts.process()` → dedup mot SQLite (`DEDUP_WINDOW_DAYS`), send én samle-mail med SAS-booking + AwardFares-lenker
5. `dashboard.render()` → skriver `output/dashboard.html`

## Config-knapper

- `ROUTES` i `config.py` — endre rute-liste
- `MIN_SEATS = 2` — vi vil ha to på samme avgang
- `DEDUP_WINDOW_DAYS = 30` — hvor lenge en flight teller som "varslet"
- `START_DATE` / `END_DATE` — søkevindu

## Gratis stack — slik er det egentlig

**Det som funker uten å betale:**
- ✅ **Quick checks-panel i dashboardet** — alle 13 ruter med 1-klikk-lenker til SAS / AwardFares / Flying Blue / KLM / Delta / Google Flights. Helt stabilt, ingen API.
- ✅ **Per-rute monitor-loop** klar til bruk så snart Cloudflare er løst (se under).

**Det som er knotete:**
- ⚠️ **AwardFares er bak Cloudflare** — headless Playwright får "Just a moment..."-veggen. Vi detekterer dette og logger en tydelig advarsel.
- 🔧 **Løsning:** kjør `.venv/bin/python bootstrap_cookies.py` én gang. Det åpner et synlig Chromium, du løser challenge (vanligvis automatisk) og evt. logger inn på AwardFares for fullt resultat. Cookies lagres i `cache/awardfares_cookies.json` og gjenbrukes av monitoren.
- 🔁 Cookies utløper etter noen uker — kjør bootstrap på nytt når du ser CF-warnings i loggen.

**Anbefalt arbeidsflyt uten betaling:**
1. Åpne `output/dashboard.html` daglig — bruk Quick checks-panelet til å klikke gjennom 5 ruter på 30 sekunder
2. Kjør `bootstrap_cookies.py` én gang, sett opp `watch --interval 720` (12 t) i bakgrunnen
3. Når monitoren faktisk får data: e-post-alerts varsler om nye seter automatisk

## Status nå

- ✅ Alle moduler importerer (testet med Python 3.12)
- ✅ AwardFares-parser plukker OSL→JFK, CPH→BKK fra mock-HTML
- ✅ seats.aero parser tolererer både `data:[]` og `availability:[]`-shape, filtrerer på `MIN_SEATS`
- ✅ Dedup-cache: roundtrip OK
- ✅ Lenker matcher SAS- og AwardFares-format
- ⚠️ Trenger `SEATS_AERO_KEY` for primær kilde (ellers kun AwardFares public)
- ⚠️ Trenger SMTP for e-post (uten det logges varsler bare lokalt)
- ⚠️ For AwardFares må `playwright install chromium` kjøres én gang
