"""
Monitor for SAS EuroBonus award-seter.

To kilder:
  - seats.aero partner-API (krever Pro-key)
  - AwardFares public "Recently Found" (Playwright headless)

Returnerer en liste med Flight-objekter som er normalisert på tvers av kilder.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup

import config

log = logging.getLogger("monitor")


# --------------------------------------------------------------------------- #
# Datamodell
# --------------------------------------------------------------------------- #

@dataclass
class Flight:
    source: str           # "seats.aero" | "awardfares"
    origin: str
    destination: str
    date: str             # ISO YYYY-MM-DD når mulig, ellers raw fra kilde
    cabin: str
    seats: int | None
    airline: str | None
    stops: str | None = None
    mileage_cost: int | None = None
    raw: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Stabil dedup-nøkkel."""
        return f"{self.origin}-{self.destination}|{self.date}|{self.cabin}|{self.airline or '?'}"

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# seats.aero
# --------------------------------------------------------------------------- #

def fetch_seats_aero(origin: str, destination: str,
                      cabins: list[str] | None = None,
                      min_seats: int | None = None) -> list[Flight]:
    """Hent tilgjengelighet fra seats.aero. Trenger gyldig Partner-Authorization.
    Pagererer gjennom hasMore med cursor til vi har alt innenfor søkevinduet."""
    cabins = cabins or ["business"]
    if not config.SEATS_AERO_KEY:
        log.debug("seats.aero: skipper %s-%s (ingen key)", origin, destination)
        return []

    headers = {
        "Partner-Authorization": config.SEATS_AERO_KEY,
        "User-Agent": config.USER_AGENT,
        "Accept": "application/json",
    }
    out: list[Flight] = []
    cursor = 0
    pages = 0
    while True:
        params = {
            "origin_airport": origin,
            "destination_airport": destination,
            "source": config.PROGRAM,           # 'eurobonus'
            "start_date": config.START_DATE,
            "end_date": config.END_DATE,
            "take": 500,
        }
        if cursor:
            params["cursor"] = cursor
        try:
            r = requests.get(config.SEATS_AERO_URL, params=params, headers=headers, timeout=30)
        except requests.RequestException as e:
            log.warning("seats.aero %s-%s nettverk: %s", origin, destination, e)
            return out

        if r.status_code == 401:
            log.error("seats.aero 401 — sjekk SEATS_AERO_KEY")
            return out
        if r.status_code != 200:
            log.warning("seats.aero %s-%s HTTP %s: %s", origin, destination, r.status_code, r.text[:200])
            return out

        try:
            payload = r.json()
        except ValueError:
            log.warning("seats.aero %s-%s ikke JSON", origin, destination)
            return out

        out.extend(_parse_seats_aero(payload, origin, destination, cabins=cabins, min_seats=min_seats))
        pages += 1
        if not payload.get("hasMore") or pages >= 10:
            break
        cursor = payload.get("cursor", 0)

    remaining = r.headers.get("X-RateLimit-Remaining", "?")
    log.debug("seats.aero %s-%s: %d pages, %d records, %s calls left",
              origin, destination, pages, len(out), remaining)
    return out


_CABIN_PREFIX = {"business": "J", "premium_economy": "W", "economy": "Y", "first": "F"}


def _parse_seats_aero(payload: dict | list, origin: str, destination: str,
                       cabins: list[str] | None = None,
                       min_seats: int | None = None) -> Iterable[Flight]:
    """
    Parse seats.aero respons. Yielder én Flight per (record × kabinklasse-treff).
    """
    cabins = cabins or ["business"]
    min_seats = min_seats if min_seats is not None else config.MIN_SEATS

    rows: list[dict] = []
    if isinstance(payload, dict):
        rows = payload.get("data") or []
    elif isinstance(payload, list):
        rows = payload

    for row in rows:
        if not isinstance(row, dict):
            continue
        date = row.get("Date") or ""
        if isinstance(date, str) and "T" in date:
            date = date.split("T", 1)[0]
        route = row.get("Route") or {}
        org = route.get("OriginAirport") or origin
        dst = route.get("DestinationAirport") or destination
        last_seen = row.get("ComputedLastSeen") or row.get("UpdatedAt")

        for cab in cabins:
            pref = _CABIN_PREFIX.get(cab)
            if not pref:
                continue
            seats = int(row.get(f"{pref}RemainingSeats", 0) or 0)
            if seats < min_seats:
                continue

            cost_str = row.get(f"{pref}MileageCost") or "0"
            try:
                cost = int(cost_str)
            except (TypeError, ValueError):
                cost = 0
            if cost <= 0:
                cost = int(row.get(f"{pref}MileageCostRaw") or 0) or None

            direct_seats = int(row.get(f"{pref}DirectRemainingSeats", 0) or 0)
            stops = "Direct" if direct_seats >= min_seats else "1+ stops"
            airline = row.get(f"{pref}Airlines") or row.get(f"{pref}AirlinesRaw") or None

            yield Flight(
                source="seats.aero",
                origin=org,
                destination=dst,
                date=str(date) or "?",
                cabin=cab,
                seats=seats,
                airline=airline,
                stops=stops,
                mileage_cost=cost,
                raw={
                    "id": row.get("ID"),
                    "available": row.get(f"{pref}Available"),
                    "remaining_raw": row.get(f"{pref}RemainingSeatsRaw"),
                    "direct_seats": direct_seats,
                    "last_seen": last_seen,
                },
            )


SEATS_AERO_TRIPS_URL = "https://seats.aero/partnerapi/trips"


def fetch_trip_details(availability_id: str) -> dict | None:
    """Hent /partnerapi/trips/{id} — gir segments med flytid, fly-type, layovers."""
    if not config.SEATS_AERO_KEY or not availability_id:
        return None
    headers = {"Partner-Authorization": config.SEATS_AERO_KEY,
               "User-Agent": config.USER_AGENT, "Accept": "application/json"}
    try:
        r = requests.get(f"{SEATS_AERO_TRIPS_URL}/{availability_id}",
                         headers=headers, timeout=20)
    except requests.RequestException as e:
        log.warning("trips/%s nettverk: %s", availability_id, e)
        return None
    if r.status_code != 200:
        log.debug("trips/%s HTTP %s", availability_id, r.status_code)
        return None
    try:
        return r.json()
    except ValueError:
        return None


def enrich_with_trip_details(flight: Flight) -> dict:
    """Returner dict med beriket trip-info, eller None om verifisering feilet."""
    avail_id = (flight.raw or {}).get("id")
    if not avail_id:
        return {"verified": False, "reason": "ingen availability ID"}

    payload = fetch_trip_details(avail_id)
    if not payload:
        return {"verified": False, "reason": "trips API ga ingenting"}

    trips = payload.get("data") or []
    # Prefer trips som matcher vår kabin og rute
    best = None
    for t in trips:
        segs = t.get("AvailabilitySegments") or []
        if not segs:
            continue
        first, last = segs[0], segs[-1]
        if first.get("OriginAirport") != flight.origin:
            continue
        if last.get("DestinationAirport") != flight.destination:
            continue
        # Foretrekk trips hvor long-haul-segmentet matcher kabin
        long_seg = max(segs, key=lambda s: s.get("Duration", 0))
        long_haul_cabin = long_seg.get("Cabin", "").lower()
        if long_haul_cabin == flight.cabin or best is None:
            best = t
            if long_haul_cabin == flight.cabin:
                break

    if not best:
        return {"verified": False, "reason": "ingen trip matchet rute"}

    segs = best.get("AvailabilitySegments") or []
    total_flight_min = sum(s.get("Duration", 0) for s in segs)
    layovers = []
    for a, b in zip(segs, segs[1:]):
        try:
            from datetime import datetime as _dt
            arr = _dt.fromisoformat(a["ArrivesAt"].replace("Z", "+00:00"))
            dep = _dt.fromisoformat(b["DepartsAt"].replace("Z", "+00:00"))
            layovers.append({
                "airport": a["DestinationAirport"],
                "minutes": int((dep - arr).total_seconds() / 60),
            })
        except Exception:
            pass

    # Mixed-cabin warning: hvis long-haul-segmentet IKKE er ønsket kabin
    long_seg = max(segs, key=lambda s: s.get("Duration", 0))
    long_cabin = long_seg.get("Cabin", "").lower()
    cabin_match = (long_cabin == flight.cabin) if long_cabin else True

    return {
        "verified": True,
        "trip_id": best.get("ID"),
        "total_flight_min": total_flight_min,
        "total_layover_min": sum(l["minutes"] for l in layovers),
        "total_journey_min": (total_flight_min + sum(l["minutes"] for l in layovers)),
        "segments": [
            {
                "flight_no": s.get("FlightNumber"),
                "from": s.get("OriginAirport"),
                "to": s.get("DestinationAirport"),
                "departs": s.get("DepartsAt"),
                "arrives": s.get("ArrivesAt"),
                "duration_min": s.get("Duration"),
                "aircraft": s.get("AircraftName"),
                "cabin": s.get("Cabin"),
            }
            for s in segs
        ],
        "layovers": layovers,
        "long_haul_cabin": long_cabin,
        "cabin_match": cabin_match,
        "booking_links": payload.get("booking_links"),
    }


def check_seats_aero(routes: list[tuple[str, str]] | None = None,
                      cabins: list[str] | None = None,
                      min_seats: int | None = None) -> list[Flight]:
    """Sjekk alle ruter via seats.aero. Returnerer aggregert liste.
    Min seats = 1 her — destinasjon-spesifikk filter kjøres i pairing."""
    routes = routes or config.ROUTES
    # hent alle 3 kabinklasser så pairing kan velge per destinasjon
    cabins = cabins or ["business", "premium_economy", "economy"]
    if min_seats is None:
        min_seats = 1   # fang opp alt, filtrer per dest senere

    out: list[Flight] = []
    for origin, dest in routes:
        try:
            found = fetch_seats_aero(origin, dest, cabins=cabins, min_seats=min_seats)
        except Exception:
            log.exception("seats.aero %s-%s feilet", origin, dest)
            continue
        if found:
            j = sum(1 for f in found if f.cabin == "business")
            w = sum(1 for f in found if f.cabin == "premium_economy")
            y = sum(1 for f in found if f.cabin == "economy")
            log.info("seats.aero %s-%s: %d hits (J=%d, W=%d, Y=%d)",
                     origin, dest, len(found), j, w, y)
        out.extend(found)
    return out


# --------------------------------------------------------------------------- #
# AwardFares fallback (Playwright)
# --------------------------------------------------------------------------- #

AWARDFARES_URL = "https://awardfares.com/programs/sas-eurobonus"
AWARDFARES_SEARCH = "https://awardfares.com/search"


def _make_browser_context(p):
    """Felles browser/context — laster cookies hvis cache/awardfares_cookies.json finnes."""
    browser = p.chromium.launch(headless=True)
    ctx_args = {"user_agent": config.USER_AGENT}
    cookies_path = config.CACHE_DIR / "awardfares_cookies.json"
    if cookies_path.exists():
        try:
            ctx_args["storage_state"] = str(cookies_path)
            log.info("AwardFares: bruker cookies fra %s", cookies_path)
        except Exception:
            log.warning("Kunne ikke laste cookies fra %s", cookies_path)
    return browser, browser.new_context(**ctx_args)


def check_awardfares() -> list[Flight]:
    """
    Public 'Recently Found' fra AwardFares. Krever ingen login men trenger
    headless browser (Vue-rendret).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright ikke installert — kjør: pip install playwright && playwright install chromium")
        return []

    log.info("AwardFares: starter Playwright-scrape (Recently Found)")
    html = ""
    try:
        with sync_playwright() as p:
            browser, ctx = _make_browser_context(p)
            page = ctx.new_page()
            page.goto(AWARDFARES_URL, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_selector("#product-flight-list .result, #product-flight-list .flight",
                                       timeout=30_000)
            except Exception:
                page.wait_for_timeout(5_000)
            html = page.content()
            browser.close()
    except Exception:
        log.exception("AwardFares Playwright-feil")
        return []

    if _is_cloudflare_challenge(html):
        log.warning("AwardFares: Cloudflare-challenge — kjør 'python bootstrap_cookies.py' "
                    "for å lagre en gyldig sesjon")
        return []

    flights = parse_awardfares_html(html)
    filtered = [
        f for f in flights
        if f.origin in config.ORIGIN_AIRPORTS and f.destination in config.TARGET_DESTINATIONS
    ]
    log.info("AwardFares (RF): %d totalt, %d matchet ruter", len(flights), len(filtered))
    return filtered


def check_awardfares_per_route(routes: list[tuple[str, str]] | None = None,
                                max_routes: int | None = None) -> list[Flight]:
    """
    Per-rute søk på AwardFares (https://awardfares.com/search?...).
    Kjører én Playwright-sesjon, gjenbruker context for å spare oppstart.
    Uten login får man typisk teaser-resultater — for fullt resultat: legg
    cache/awardfares_cookies.json (eksportert storage_state fra innlogget sesjon).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright ikke installert")
        return []

    routes = routes or config.ROUTES
    if max_routes:
        routes = routes[:max_routes]
    out: list[Flight] = []

    log.info("AwardFares per-rute: %d ruter", len(routes))
    cf_blocked = False
    try:
        with sync_playwright() as p:
            browser, ctx = _make_browser_context(p)
            page = ctx.new_page()
            for origin, dest in routes:
                if cf_blocked:
                    break
                params = {
                    "origin": f"{origin}.",
                    "destination": f"{dest}.",
                    "cabin": "C",
                    "program": "EuroBonus",
                }
                from urllib.parse import urlencode
                url = f"{AWARDFARES_SEARCH}?{urlencode(params)}"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    try:
                        page.wait_for_selector(
                            "#product-flight-list .result, .flight, .no-results",
                            timeout=20_000,
                        )
                    except Exception:
                        page.wait_for_timeout(4_000)
                    html = page.content()
                except Exception:
                    log.exception("AwardFares per-rute %s-%s feilet", origin, dest)
                    continue

                if _is_cloudflare_challenge(html):
                    log.warning("AwardFares per-rute: Cloudflare-challenge på %s-%s — "
                                "avbryter (kjør bootstrap_cookies.py)", origin, dest)
                    cf_blocked = True
                    continue

                flights = parse_awardfares_html(html)
                # Tag med rute selv om parse fant noe litt annet
                for f in flights:
                    if f.origin not in config.ORIGIN_AIRPORTS:
                        f.origin = origin
                    if f.destination not in config.TARGET_DESTINATIONS:
                        f.destination = dest
                if flights:
                    log.info("AwardFares %s-%s: %d hits", origin, dest, len(flights))
                else:
                    log.debug("AwardFares %s-%s: 0 hits", origin, dest)
                out.extend(flights)
                # Liten pause så vi ikke hamrer
                page.wait_for_timeout(800)
            browser.close()
    except Exception:
        log.exception("AwardFares per-rute Playwright-feil")
    return out


def _is_cloudflare_challenge(html: str) -> bool:
    return ("Just a moment" in html[:2000]
            or "challenge-platform" in html[:5000]
            or "cf-challenge" in html[:5000])


def parse_awardfares_html(html: str) -> list[Flight]:
    """
    Parse AwardFares 'Recently Found'-listen.
    HTML-mønster (forenklet):
      <div class="flight">
        <div class="primary"><a>OSL</a> ... <a>JFK</a></div>
        <div class="time"><div class="primary">Thu, Jun 11</div></div>
        <div class="stops"><div class="primary">1 stop</div></div>
      </div>
    Public-feed har ofte ikke seteantall — da setter vi seats=None og lar alert
    behandle det som 'sjekk manuelt'.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[Flight] = []

    # Forsøk å finne "result"-rader (de øverste flight-cardsene), fall tilbake til .flight
    rows = soup.select("#product-flight-list .result")
    if not rows:
        rows = soup.select(".flight")

    for row in rows:
        # Primær flight-info: airport-koder
        primary = row.select_one(".primary")
        airports = []
        if primary:
            airports = [a.get_text(strip=True) for a in primary.select("a")]
            if not airports:
                # noen ganger er det rene <span>'er
                airports = [s.get_text(strip=True) for s in primary.select("span")]
        airports = [a for a in airports if a and len(a) == 3 and a.isalpha()]
        if len(airports) < 2:
            continue
        origin, destination = airports[0].upper(), airports[-1].upper()

        # Dato
        date_el = row.select_one(".time .primary, .date .primary, .time")
        date_raw = date_el.get_text(" ", strip=True) if date_el else ""
        date = _normalize_awardfares_date(date_raw)

        # Stops
        stops_el = row.select_one(".stops .primary, .stops")
        stops = stops_el.get_text(" ", strip=True) if stops_el else None

        # Cabin (av og til som badge)
        cabin_el = row.select_one(".cabin, .class")
        cabin_text = cabin_el.get_text(" ", strip=True).lower() if cabin_el else config.CABIN
        cabin = "business" if "business" in cabin_text else cabin_text or config.CABIN

        # Airline (forsøksvis)
        airline_el = row.select_one(".airline, .carrier")
        airline = airline_el.get_text(" ", strip=True) if airline_el else None

        out.append(Flight(
            source="awardfares",
            origin=origin,
            destination=destination,
            date=date,
            cabin=cabin,
            seats=None,                # public feed gir ikke seteantall
            airline=airline,
            stops=stops,
            raw={"date_raw": date_raw},
        ))
    return out


def _normalize_awardfares_date(raw: str) -> str:
    """'Thu, Jun 11' → '2026-06-11' (antar nærmeste fremtid)."""
    if not raw:
        return "?"
    # Strip ukedag
    parts = [p.strip() for p in raw.split(",")]
    candidate = parts[-1] if len(parts) > 1 else parts[0]
    today = datetime.utcnow()
    for fmt in ("%b %d %Y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(f"{candidate} {today.year}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    for fmt in ("%b %d", "%d %b"):
        try:
            dt = datetime.strptime(candidate, fmt).replace(year=today.year)
            if dt < today:
                dt = dt.replace(year=today.year + 1)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return raw


# --------------------------------------------------------------------------- #
# Orkestrering
# --------------------------------------------------------------------------- #

def run_check() -> dict:
    """Kjør komplett sjekk + bygg trip-par per destinasjon."""
    from pairing import pair_all  # her for å unngå circular import ved test

    started = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    primary = check_seats_aero()
    fallback: list[Flight] = []
    if not config.SEATS_AERO_KEY:
        # Vi har ingen key — fall tilbake til AwardFares (hvis CF tillater)
        rf = check_awardfares()
        per_route = check_awardfares_per_route()
        seen_keys = set()
        for f in rf + per_route:
            if f.key not in seen_keys:
                seen_keys.add(f.key)
                fallback.append(f)

    all_flights = primary + fallback

    # Trip-paring per destinasjon
    trip_pairs = pair_all(config.DESTINATIONS, all_flights)
    pairs_dict = {name: [p.to_dict() for p in pairs] for name, pairs in trip_pairs.items()}

    # Topp-deals (beste på tvers av destinasjoner)
    flat = [(name, p) for name, ps in trip_pairs.items() for p in ps]
    flat.sort(key=lambda x: x[1].score)

    # Verifiser top 15 ved å hente trip-detaljer per leg
    top_deals = []
    candidates = flat[:15]
    log.info("Verifiserer top %d deals via Trips-API", len(candidates))
    verified_count = 0
    for name, p in candidates:
        out_flight = next((f for f in all_flights
                           if f.origin == p.out["origin"] and f.destination == p.out["destination"]
                           and f.date == p.out["date"] and f.cabin == p.cabin), None)
        ret_flight = next((f for f in all_flights
                           if f.origin == p.ret["origin"] and f.destination == p.ret["destination"]
                           and f.date == p.ret["date"] and f.cabin == p.cabin), None)
        out_det = enrich_with_trip_details(out_flight) if out_flight else {"verified": False}
        ret_det = enrich_with_trip_details(ret_flight) if ret_flight else {"verified": False}

        if not (out_det.get("verified") and ret_det.get("verified")):
            log.info("DROPPER %s %s→%s (ut=%s, ret=%s)", name, p.out["date"], p.ret["date"],
                     out_det.get("reason"), ret_det.get("reason"))
            continue

        verified_count += 1
        deal = {"destination": name, **p.to_dict(),
                "out_details": out_det, "ret_details": ret_det,
                "verified": True}
        top_deals.append(deal)

    log.info("Top deals: %d/%d verifisert", verified_count, len(candidates))

    result = {
        "started": started,
        "finished": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "routes_checked": [f"{o}-{d}" for o, d in config.ROUTES],
        "primary_count": len(primary),
        "fallback_count": len(fallback),
        "total": len(all_flights),
        "matching": [f.to_dict() for f in all_flights],
        "trip_pairs": pairs_dict,
        "top_deals": top_deals,
        "seats_aero_key_present": bool(config.SEATS_AERO_KEY),
    }
    config.LAST_RUN_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":  # quick smoke test
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    res = run_check()
    print(json.dumps({k: v for k, v in res.items() if k != "matching"}, indent=2))
    print(f"Matching flights: {len(res['matching'])}")
