"""
Hotel deep-link-generatorer. Genererer søk-URL'er per destinasjon + datoer
for de største bookings-sites. Ingen API-keys, ingen scraping — bare URL-bygging.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus, urlencode


# Destinasjons-airport → fornuftig søke-by + lat/long for nøyaktige treff
AIRPORT_TO_CITY = {
    "JFK":  {"city": "New York",      "country": "USA",     "lat": 40.7128, "lng": -74.0060, "ss_id": "20088325"},
    "EWR":  {"city": "New York",      "country": "USA",     "lat": 40.7128, "lng": -74.0060, "ss_id": "20088325"},
    "BOS":  {"city": "Boston",        "country": "USA",     "lat": 42.3601, "lng": -71.0589, "ss_id": "20088326"},
    "ORD":  {"city": "Chicago",       "country": "USA",     "lat": 41.8781, "lng": -87.6298, "ss_id": "20066676"},
    "LAX":  {"city": "Los Angeles",   "country": "USA",     "lat": 34.0522, "lng": -118.2437, "ss_id": "20014181"},
    "SFO":  {"city": "San Francisco", "country": "USA",     "lat": 37.7749, "lng": -122.4194, "ss_id": "20015732"},
    "MIA":  {"city": "Miami",         "country": "USA",     "lat": 25.7617, "lng": -80.1918, "ss_id": "20023181"},

    "BKK":  {"city": "Bangkok",       "country": "Thailand","lat": 13.7563, "lng": 100.5018, "ss_id": "-3414440"},
    "SIN":  {"city": "Singapore",     "country": "Singapore","lat": 1.3521, "lng": 103.8198, "ss_id": "-73635"},
    "ICN":  {"city": "Seoul",         "country": "South Korea","lat": 37.5665, "lng": 126.9780, "ss_id": "-716985"},
    "NRT":  {"city": "Tokyo",         "country": "Japan",   "lat": 35.6762, "lng": 139.6503, "ss_id": "-246227"},
    "HND":  {"city": "Tokyo",         "country": "Japan",   "lat": 35.6762, "lng": 139.6503, "ss_id": "-246227"},
    "HAN":  {"city": "Hanoi",         "country": "Vietnam", "lat": 21.0285, "lng": 105.8542, "ss_id": "-3712051"},
    "SGN":  {"city": "Ho Chi Minh City","country": "Vietnam","lat": 10.8231, "lng": 106.6297, "ss_id": "-3730078"},
    "HKG":  {"city": "Hong Kong",     "country": "Hong Kong","lat": 22.3193, "lng": 114.1694, "ss_id": "-1353149"},
    "SCL":  {"city": "Santiago",      "country": "Chile",   "lat": -33.4489, "lng": -70.6693, "ss_id": "-986741"},
}


@dataclass
class HotelLinks:
    city: str
    country: str
    booking: str
    hotels_com: str
    airbnb: str
    google: str
    expedia: str


def for_trip(dest_airport: str, checkin: str, checkout: str,
             adults: int = 2) -> HotelLinks:
    """Bygg hotel-søk for en spesifikk trip."""
    info = AIRPORT_TO_CITY.get(dest_airport, {
        "city": dest_airport, "country": "", "lat": 0, "lng": 0, "ss_id": ""
    })
    city = info["city"]
    country = info["country"]

    return HotelLinks(
        city=city,
        country=country,
        booking=_booking(city, info["ss_id"], checkin, checkout, adults),
        hotels_com=_hotels_com(city, checkin, checkout, adults),
        airbnb=_airbnb(city, info["lat"], info["lng"], checkin, checkout, adults),
        google=_google(city, checkin, checkout, adults),
        expedia=_expedia(city, checkin, checkout, adults),
    )


# --------------------------------------------------------------------------- #
# Per-vendor URL-byggere
# --------------------------------------------------------------------------- #

def _booking(city: str, ss_id: str, checkin: str, checkout: str, adults: int) -> str:
    p = {
        "ss": city,
        "checkin": checkin,
        "checkout": checkout,
        "group_adults": adults,
        "no_rooms": 1,
        "group_children": 0,
    }
    if ss_id:
        p["dest_id"] = ss_id
        p["dest_type"] = "city"
    return "https://www.booking.com/searchresults.html?" + urlencode(p)


def _hotels_com(city: str, checkin: str, checkout: str, adults: int) -> str:
    # Hotels.com bruker quote-encoded query-string
    p = {
        "destination": city,
        "startDate": checkin,
        "endDate": checkout,
        "adults": adults,
    }
    return "https://www.hotels.com/Hotel-Search?" + urlencode(p)


def _airbnb(city: str, lat: float, lng: float, checkin: str, checkout: str, adults: int) -> str:
    # Airbnb deep link med koordinater
    p = {
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "query": city,
    }
    return f"https://www.airbnb.com/s/{quote_plus(city)}/homes?" + urlencode(p)


def _google(city: str, checkin: str, checkout: str, adults: int) -> str:
    # Google Hotels — fritekst-søk
    q = f"hotels in {city}"
    return (
        f"https://www.google.com/travel/hotels/{quote_plus(city)}?"
        + urlencode({
            "q": q,
            "checkin": checkin,
            "checkout": checkout,
            "ts": "CAESCgoCCAMKAggDEAA",  # Google's hotel-tab marker
        })
    )


def _expedia(city: str, checkin: str, checkout: str, adults: int) -> str:
    p = {
        "destination": city,
        "startDate": checkin,
        "endDate": checkout,
        "adults": adults,
    }
    return "https://www.expedia.com/Hotel-Search?" + urlencode(p)
