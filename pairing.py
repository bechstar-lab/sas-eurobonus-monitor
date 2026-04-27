"""
Round-trip pairing: matcher outbound + return-flighter til konkrete trip-forslag
per destinasjon. Respekterer trip_length_days, origin_priority og cabin-preferanse.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Iterable

from destinations import Destination, is_trip_booked
from monitor import Flight


@dataclass
class TripPair:
    destination: str
    origin: str
    dest_airport: str
    cabin: str
    out: dict
    ret: dict
    trip_days: int
    total_pts: int
    score: float = 0.0
    notes: list[str] = field(default_factory=list)
    max_age_hours: float = 0.0       # eldste leg av paret
    phantom_risk: str = "low"        # low / medium / high

    def to_dict(self) -> dict:
        return asdict(self)


def _age_hours(iso: str | None) -> float:
    if not iso:
        return 999.0
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(ts.tzinfo) - ts).total_seconds() / 3600
    except Exception:
        return 999.0


def _phantom_risk(out: Flight, ret: Flight, age_hours: float) -> str:
    """Heuristikk: phantom availability mer sannsynlig hvis stale eller raw>>filtered."""
    if age_hours > 24:
        return "high"
    if age_hours > 12:
        return "medium"
    # Raw seat-count vesentlig høyere enn filtered → bucket-rariteter
    for f in (out, ret):
        raw = (f.raw or {}).get("remaining_raw") or 0
        if f.seats and raw and raw > f.seats * 3:
            return "medium"
    return "low"


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d)
    except (ValueError, TypeError):
        return None


def _origin_rank(origin: str, priority: list[str]) -> int:
    try:
        return priority.index(origin)
    except ValueError:
        return 99


def _cabin_rank(cabin: str) -> int:
    return {"business": 0, "premium_economy": 1, "economy": 2}.get(cabin, 9)


def _stop_rank(stops: str | None) -> int:
    return 0 if (stops or "").lower().startswith("direct") else 1


def pair_for_destination(dest: Destination, flights: list[Flight]) -> list[TripPair]:
    """Lag par for én destinasjon basert på dens kriterier."""
    # filter til kun denne destens fly + i datovinduet
    win_start = _parse(dest.window_start)
    win_end = _parse(dest.window_end)

    def in_window(d: date | None) -> bool:
        if d is None: return False
        if win_start and d < win_start: return False
        if win_end and d > win_end: return False
        return True

    # dest.airports + dest.origin_priority styrer hvilke fly som regnes med
    valid_origins = set(dest.origin_priority)
    valid_airports = set(dest.airports)

    outbound: list[Flight] = []
    inbound:  list[Flight] = []
    for f in flights:
        d = _parse(f.date)
        if not in_window(d):
            continue
        if f.cabin not in dest.cabins:
            continue
        if dest.direct_only and not (f.stops or "").lower().startswith("direct"):
            continue
        if f.origin in valid_origins and f.destination in valid_airports:
            outbound.append(f)
        elif f.origin in valid_airports and f.destination in valid_origins:
            inbound.append(f)

    # Indeksér return på (origin/dest_airport, cabin, dato)
    pairs: list[TripPair] = []
    for o in outbound:
        out_d = _parse(o.date)
        if not out_d:
            continue
        for r in inbound:
            # Samme dest_airport for ret-origin = avgang fra samme by
            if r.origin != o.destination:
                continue
            # Foretrukket: samme home-origin (OSL→JFK + JFK→OSL)
            if r.destination != o.origin:
                continue
            # Samme kabinklasse for konsistens (du kan tenke at vi tillater J-out + W-ret, men ikke nå)
            if r.cabin != o.cabin:
                continue
            ret_d = _parse(r.date)
            if not ret_d:
                continue
            trip_days = (ret_d - out_d).days
            if trip_days < dest.trip_min_days or trip_days > dest.trip_max_days:
                continue

            total = (o.mileage_cost or 0) + (r.mileage_cost or 0)

            # Score: lavere = bedre
            #   origin-rank først (OSL > CPH), kabin (business > W),
            #   stops (direct > connecting), kostnad
            score = (
                _origin_rank(o.origin, dest.origin_priority) * 1000
                + _cabin_rank(o.cabin) * 100
                + (_stop_rank(o.stops) + _stop_rank(r.stops)) * 50
                + total / 10000
            )

            notes = []
            if dest.alert_only_better_than and total > dest.alert_only_better_than * 2:
                notes.append(f"Over budsjett ({total:,} pts > {dest.alert_only_better_than*2:,})")
            if (o.stops or "").lower() != "direct":
                notes.append("Out: connecting")
            if (r.stops or "").lower() != "direct":
                notes.append("Ret: connecting")

            out_age = _age_hours((o.raw or {}).get("last_seen"))
            ret_age = _age_hours((r.raw or {}).get("last_seen"))
            max_age = max(out_age, ret_age)
            risk = _phantom_risk(o, r, max_age)

            # Score-penalty for stale/risiko (medium = +500, high = +5000)
            if risk == "medium":
                score += 500
            elif risk == "high":
                score += 5000
                notes.append(f"Data {max_age:.0f}t gammel — sjekk SAS før booking")

            # Deprioritere destinasjoner (e.g. allerede booket noe der)
            if dest.deprioritize:
                score += 10000

            # Skip allerede bookede trips
            if is_trip_booked(o.origin, o.destination, o.date, r.date, o.cabin):
                continue

            pairs.append(TripPair(
                destination=dest.name,
                origin=o.origin,
                dest_airport=o.destination,
                cabin=o.cabin,
                out=o.to_dict(),
                ret=r.to_dict(),
                trip_days=trip_days,
                total_pts=total,
                score=score,
                notes=notes,
                max_age_hours=round(max_age, 1),
                phantom_risk=risk,
            ))

    pairs.sort(key=lambda p: p.score)
    return pairs


def pair_all(destinations: list[Destination], flights: list[Flight]) -> dict[str, list[TripPair]]:
    """Returner {dest_name: [TripPair, ...]} for alle destinasjoner."""
    out: dict[str, list[TripPair]] = {}
    for dest in destinations:
        if dest.requires_connection:
            out[dest.name] = []
            continue
        out[dest.name] = pair_for_destination(dest, flights)
    return out
