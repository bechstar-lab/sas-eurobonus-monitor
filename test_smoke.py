"""
Smoke-test: verifiserer at alle moduler importerer + at parseren håndterer
HTML-mønsteret AwardFares bruker.

Kjør:  python test_smoke.py
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    failures = []

    # 1) Imports
    try:
        import config           # noqa
        import monitor          # noqa
        import alerts           # noqa
        import dashboard        # noqa
        import run              # noqa
        print("[ok] imports")
    except Exception as e:
        print(f"[FAIL] import: {e}")
        return 1

    # 2) AwardFares parser
    from monitor import parse_awardfares_html, _normalize_awardfares_date
    sample = """
    <div id="product-flight-list">
      <div class="result">
        <div class="flight">
          <div class="primary">
            <a href="#">OSL</a>
            <span>→</span>
            <a href="#">JFK</a>
          </div>
        </div>
        <div class="time"><div class="primary">Thu, Jun 11</div></div>
        <div class="stops"><div class="primary">1 stop</div></div>
        <div class="cabin">Business</div>
      </div>
      <div class="result">
        <div class="flight">
          <div class="primary">
            <a>CPH</a><a>BKK</a>
          </div>
        </div>
        <div class="time"><div class="primary">Mon, Aug 4</div></div>
        <div class="stops"><div class="primary">Direct</div></div>
      </div>
      <div class="result">
        <div class="flight">
          <div class="primary"><a>ARN</a><a>NYC</a></div>
        </div>
        <div class="time"><div class="primary">Sat, Sep 12</div></div>
      </div>
    </div>
    """
    flights = parse_awardfares_html(sample)
    print(f"[ok] parsed {len(flights)} flights")
    for f in flights:
        print(f"     {f.origin}→{f.destination}  {f.date}  cabin={f.cabin}  stops={f.stops}")

    if len(flights) < 2:
        failures.append(f"forventet >=2 flights, fikk {len(flights)}")
    by_route = {(f.origin, f.destination) for f in flights}
    if ("OSL", "JFK") not in by_route:
        failures.append("OSL→JFK ikke parsed")
    if ("CPH", "BKK") not in by_route:
        failures.append("CPH→BKK ikke parsed")

    # 3) Dato-normalisering
    d = _normalize_awardfares_date("Jun 11")
    if not (d.startswith("202") and d.endswith("-06-11")):
        failures.append(f"dato-normalisering feilet: {d}")
    else:
        print(f"[ok] date normalize: 'Jun 11' → {d}")

    # 4) seats.aero parser med mock payload
    from monitor import _parse_seats_aero, Flight
    mock = {"data": [
        {"Route": {"OriginAirport": "OSL", "DestinationAirport": "JFK", "Source": "eurobonus"},
         "Date": "2026-08-15T00:00:00Z",
         "JAvailable": True, "JRemainingSeats": 4, "JMileageCost": "60000",
         "JDirectRemainingSeats": 4, "JAirlines": "SK"},
        {"Route": {"OriginAirport": "OSL", "DestinationAirport": "JFK"},
         "Date": "2026-08-16", "JRemainingSeats": 1},   # under MIN_SEATS
        {"Route": {"OriginAirport": "OSL", "DestinationAirport": "JFK"},
         "Date": "2026-08-17", "JRemainingSeats": 0},   # 0 seter
    ]}
    parsed = list(_parse_seats_aero(mock, "OSL", "JFK"))
    print(f"[ok] seats.aero parser ga {len(parsed)} flight(s) etter filter")
    if len(parsed) != 1:
        failures.append(f"seats.aero parser: forventet 1, fikk {len(parsed)}")
    elif parsed[0].seats != 4 or parsed[0].mileage_cost != 60000:
        failures.append(f"seats.aero felter feil: {parsed[0]}")

    # 5) Alerts: dedup-cache roundtrip
    from alerts import filter_new, mark_alerted, _conn
    test_flight = Flight(source="test", origin="OSL", destination="JFK",
                          date="2026-09-09", cabin="business", seats=2, airline="SK")
    # rydd evt gammel testdata
    with _conn() as c:
        c.execute("DELETE FROM seen WHERE key = ?", (test_flight.key,))
    new = filter_new([test_flight])
    if len(new) != 1:
        failures.append(f"filter_new: forventet 1 ny, fikk {len(new)}")
    mark_alerted(new)
    again = filter_new([test_flight])
    if len(again) != 0:
        failures.append(f"filter_new (etter mark): forventet 0, fikk {len(again)}")
    print("[ok] dedup-cache roundtrip")
    # rydd opp
    with _conn() as c:
        c.execute("DELETE FROM seen WHERE key = ?", (test_flight.key,))

    # 6) Dashboard render uten data
    from dashboard import render
    out = render({"finished": "test", "total": 0, "routes_checked": ["OSL-JFK"],
                  "matching": [], "seats_aero_key_present": False,
                  "primary_count": 0, "fallback_count": 0})
    if not out.endswith("dashboard.html"):
        failures.append(f"dashboard render output uventet: {out}")
    print(f"[ok] dashboard rendered to {out}")

    # 7) Lenke-format
    from alerts import sas_booking_link, awardfares_link
    sl = sas_booking_link(test_flight)
    al = awardfares_link(test_flight)
    if "from=OSL" not in sl or "to=JFK" not in sl or "outDate=2026-09-09" not in sl:
        failures.append(f"SAS-link format feil: {sl}")
    if "origin=OSL." not in al or "cabin=C" not in al:
        failures.append(f"AwardFares-link format feil: {al}")
    print(f"[ok] SAS:        {sl}")
    print(f"[ok] AwardFares: {al}")

    # 8) Link-generatorer
    from links import for_route, all_routes_links
    rl = for_route("OSL", "JFK")
    for label, url in [("sas", rl.sas), ("flying_blue", rl.flying_blue),
                       ("klm", rl.klm), ("delta", rl.delta), ("google", rl.google_flights)]:
        if not url.startswith("http"):
            failures.append(f"{label} link malformed: {url}")
    if "OSL-JFK" not in rl.flying_blue:
        failures.append(f"FB connections-format feil: {rl.flying_blue}")
    if "originCity=OSL" not in rl.delta:
        failures.append(f"Delta originCity feil: {rl.delta}")
    print(f"[ok] link-generatorer: 6 vendors per rute")

    arl = all_routes_links()
    # Bare outbound — return-ruter skal ekskluderes
    if len(arl) == 0:
        failures.append("all_routes_links returnerte 0")
    print(f"[ok] genererte links for {len(arl)} outbound-ruter")

    # 9) Destinations + pairing
    from destinations import load
    from pairing import pair_for_destination
    dests = load()
    if not dests:
        failures.append("destinations.yaml lastet 0 dest")
    else:
        print(f"[ok] lastet {len(dests)} destinasjoner fra YAML")
        # Test pairing med mock-data
        from monitor import Flight
        out = Flight(source="t", origin="OSL", destination="JFK",
                     date="2026-08-15", cabin="business", seats=2,
                     airline="SK", stops="Direct", mileage_cost=60000)
        ret = Flight(source="t", origin="JFK", destination="OSL",
                     date="2026-08-22", cabin="business", seats=2,
                     airline="SK", stops="Direct", mileage_cost=60000)
        ny = next(d for d in dests if d.name == "New York")
        pairs = pair_for_destination(ny, [out, ret])
        if not pairs:
            failures.append("pair_for_destination ga 0 par")
        else:
            print(f"[ok] pairing: {len(pairs)} par, best total={pairs[0].total_pts}pts {pairs[0].trip_days}d")

    print()
    if failures:
        print("FEIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("ALLE TESTER OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
