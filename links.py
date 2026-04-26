"""
Link-generatorer for manuelle award-sjekker hos SkyTeam-partnere.

SAS er nå i SkyTeam (sept 2024). AF/KL/DL kan booke SAS-metal med sine miles,
og deres søk er gratis tilgjengelige (uten Pro-key). Vi kan ikke alltid scrape
dem pålitelig, men deep-link til søk er 100 % stabilt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date, timedelta
from urllib.parse import urlencode

import config


@dataclass
class RouteLinks:
    origin: str
    destination: str
    sas: str
    awardfares: str
    flying_blue: str
    klm: str
    delta: str
    google_flights: str


def _fmt_date(d: _date) -> str:
    return d.isoformat()


def for_route(origin: str, destination: str,
              out_date: str | None = None,
              ret_date: str | None = None) -> RouteLinks:
    """
    Bygg sett med søk-lenker for en rute. Hvis dato ikke gis, bruker vi
    midten av søkevinduet (bra default for "se hva som finnes").
    """
    if not out_date:
        out_date = _midpoint_date()
    if not ret_date:
        ret_date = _add_days(out_date, 14)

    return RouteLinks(
        origin=origin,
        destination=destination,
        sas=_sas(origin, destination, out_date, ret_date),
        awardfares=_awardfares(origin, destination),
        flying_blue=_flying_blue(origin, destination, out_date, ret_date),
        klm=_klm(origin, destination, out_date, ret_date),
        delta=_delta(origin, destination, out_date, ret_date),
        google_flights=_google_flights(origin, destination, out_date, ret_date),
    )


# --------------------------------------------------------------------------- #
# Per-vendor URL-bygging
# --------------------------------------------------------------------------- #

def _sas(o: str, d: str, out: str, ret: str) -> str:
    # SAS bonus-flow tar emne via querystring og åpner kalender på outDate
    return "https://www.flysas.com/en/book/flights/?" + urlencode({
        "bookingFlow": "BONUS",
        "from": o, "to": d,
        "outDate": out, "retDate": ret,
        "adt": 2, "chd": 0, "inf": 0,
    })


def _awardfares(o: str, d: str) -> str:
    return "https://awardfares.com/search?" + urlencode({
        "origin": f"{o}.", "destination": f"{d}.",
        "cabin": "C", "program": "EuroBonus",
    })


def _flying_blue(o: str, d: str, out: str, ret: str) -> str:
    # Flying Blue / Air France award-search deep link.
    # AF bruker en SPA — denne URLen åpner søkesiden og pre-fyller felt.
    return "https://wwws.airfrance.com/search/offers?" + urlencode({
        "connections": f"{o}-{d}",
        "outboundDate": out,
        "inboundDate": ret,
        "cabinClass": "BUSINESS",
        "currency": "MILES",
        "type": "ROUND_TRIP",
        "passengers": "ADT-2",
    })


def _klm(o: str, d: str, out: str, ret: str) -> str:
    return "https://www.klm.com/search/offers?" + urlencode({
        "connections": f"{o}-{d}",
        "outboundDate": out,
        "inboundDate": ret,
        "cabinClass": "BUSINESS",
        "currency": "MILES",
        "type": "ROUND_TRIP",
        "passengers": "ADT-2",
    })


def _delta(o: str, d: str, out: str, ret: str) -> str:
    # Delta SkyMiles award-search. "Shop with Miles"-toggle aktiveres med awardTravel=true
    return "https://www.delta.com/flight-search/book-a-flight?" + urlencode({
        "tripType": "ROUND_TRIP",
        "priceSchedule": "PRICE",
        "awardTravel": "true",
        "passengerCount": 2,
        "originCity": o,
        "destinationCity": d,
        "departureDate": out,
        "returnDate": ret,
        "fareFamily": "BE",
    })


def _google_flights(o: str, d: str, out: str, ret: str) -> str:
    # Cash-baseline — nyttig for å se om dato i det hele tatt har trafikk
    return f"https://www.google.com/travel/flights?q=Flights%20to%20{d}%20from%20{o}%20on%20{out}%20returning%20{ret}"


# --------------------------------------------------------------------------- #
# Hjelpere
# --------------------------------------------------------------------------- #

def _midpoint_date() -> str:
    """Midt i søkevinduet (eller +120d hvis fortid)."""
    try:
        s = _date.fromisoformat(config.START_DATE)
        e = _date.fromisoformat(config.END_DATE)
        mid = s + (e - s) / 2
        if mid < _date.today():
            mid = _date.today() + timedelta(days=120)
        return mid.isoformat()
    except Exception:
        return (_date.today() + timedelta(days=120)).isoformat()


def _add_days(iso: str, days: int) -> str:
    return (_date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def all_routes_links() -> list[RouteLinks]:
    """Genererer link-sett kun for outbound (origin → dest_airport),
    ikke return-retninger som også finnes i config.ROUTES."""
    out: list[RouteLinks] = []
    seen = set()
    for dest in config.DESTINATIONS:
        for o in dest.origin_priority:
            for a in dest.airports:
                if (o, a) in seen:
                    continue
                seen.add((o, a))
                out.append(for_route(o, a))
    return out
