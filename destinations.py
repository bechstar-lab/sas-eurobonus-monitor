"""Last destinations.yaml og bygg Destination-objekter med defaults flettet inn."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any

import yaml

YAML_PATH = Path(__file__).resolve().parent / "destinations.yaml"
BOOKED_PATH = Path(__file__).resolve().parent / "booked.yaml"


@dataclass
class Destination:
    name: str
    airports: list[str]
    cabins: list[str]
    min_seats: int
    origin_priority: list[str]
    trip_min_days: int
    trip_max_days: int
    direct_only: bool
    window_start: str
    window_end: str
    booking_deadline: str
    alert_only_better_than: int | None
    requires_connection: bool
    deprioritize: bool
    hide_from_top: bool        # fullt ekskluder fra top deals + share view
    notes: str

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-").replace("/", "-")

    @property
    def routes(self) -> list[tuple[str, str]]:
        """(origin, dest_airport) for outbound — én per (origin × airport)."""
        return [(o, a) for o in self.origin_priority for a in self.airports]

    @property
    def return_routes(self) -> list[tuple[str, str]]:
        """For pairing: returflighter."""
        return [(a, o) for o in self.origin_priority for a in self.airports]


def _merge(defaults: dict, override: dict) -> dict:
    out = dict(defaults)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> list[Destination]:
    if not YAML_PATH.exists():
        return []
    raw = yaml.safe_load(YAML_PATH.read_text())
    defaults = raw.get("defaults", {})
    out: list[Destination] = []
    for d in raw.get("destinations", []):
        merged = _merge(defaults, d)
        tld = merged.get("trip_length_days", {})
        tw = merged.get("travel_window", {})
        out.append(Destination(
            name=merged["name"],
            airports=list(merged["airports"]),
            cabins=list(merged.get("cabins", ["business"])),
            min_seats=int(merged.get("min_seats", 2)),
            origin_priority=list(merged.get("origin_priority", ["OSL"])),
            trip_min_days=int(tld.get("min", 5)),
            trip_max_days=int(tld.get("max", 21)),
            direct_only=bool(merged.get("direct_only", False)),
            window_start=str(tw.get("start", "2026-07-01")),
            window_end=str(tw.get("end", "2027-12-31")),
            booking_deadline=str(merged.get("booking_deadline", "2026-12-31")),
            alert_only_better_than=int(merged["alert_only_better_than"])
                if merged.get("alert_only_better_than") else None,
            requires_connection=bool(merged.get("requires_connection", False)),
            deprioritize=bool(merged.get("deprioritize", False)),
            hide_from_top=bool(merged.get("hide_from_top", False)),
            notes=str(merged.get("notes", "")),
        ))
    return out


def all_routes(skip_manual: bool = True) -> list[tuple[str, str]]:
    """Aggregert sett med outbound + return-ruter til seats.aero."""
    seen = set()
    for dest in load():
        if skip_manual and dest.requires_connection:
            continue
        for r in dest.routes + dest.return_routes:
            seen.add(r)
    return sorted(seen)


def load_booked() -> list[dict]:
    """Last booked.yaml — reiser som allerede er booket."""
    if not BOOKED_PATH.exists():
        return []
    raw = yaml.safe_load(BOOKED_PATH.read_text()) or {}
    return raw.get("bookings", [])


def is_trip_booked(origin: str, dest_airport: str, out_date: str, ret_date: str,
                    cabin: str | None = None) -> bool:
    """Sjekk om en konkret trip er allerede booket."""
    for b in load_booked():
        if (b.get("origin") == origin
            and b.get("dest_airport") == dest_airport
            and b.get("out_date") == out_date
            and b.get("ret_date") == ret_date):
            if cabin is None or b.get("cabin") == cabin:
                return True
    return False
