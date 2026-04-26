"""
CLI for SAS EuroBonus Award Monitor.

  python run.py check                    # enkeltsjekk
  python run.py watch --interval 360     # daemon, sjekk hvert 360 minutt
  python run.py status                   # vis siste funn + cache
  python run.py dashboard                # bare regenerer HTML
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

import config


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    # File
    fh = RotatingFileHandler(config.LOG_PATH, maxBytes=2_000_000, backupCount=3)
    fh.setFormatter(logging.Formatter(fmt))
    fh.setLevel(level)
    root.addHandler(fh)
    # Stdout
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(fmt))
    sh.setLevel(level)
    root.addHandler(sh)


def cmd_check() -> int:
    # Importer her så --help ikke krever playwright/etc.
    from monitor import run_check, Flight
    from alerts import process
    from dashboard import render

    log = logging.getLogger("cli")
    log.info("=== SAS EuroBonus check started ===")
    result = run_check()
    flights = [Flight(**{k: v for k, v in f.items()}) for f in result["matching"]]
    alert_report = process(flights)
    dashboard_path = render(result)

    log.info("Sjekk ferdig: %d total, %d matchet, %d nye, sendt=%s",
             result["total"], len(flights), alert_report["new"], alert_report["sent"])
    log.info("Dashboard: %s", dashboard_path)

    print(json.dumps({
        "finished": result["finished"],
        "primary_count": result["primary_count"],
        "fallback_count": result["fallback_count"],
        "matching": len(flights),
        "new": alert_report["new"],
        "alert_sent": alert_report["sent"],
        "dashboard": dashboard_path,
    }, indent=2))
    return 0


def cmd_watch(interval_minutes: int) -> int:
    log = logging.getLogger("cli")
    log.info("Watcher starter (interval=%d min). Ctrl-C for å stoppe.", interval_minutes)
    stopping = {"flag": False}

    def _stop(signum, _frame):
        log.info("Mottok signal %s — stopper etter neste runde", signum)
        stopping["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stopping["flag"]:
        try:
            cmd_check()
        except Exception:
            log.exception("Sjekk feilet — fortsetter")
        if stopping["flag"]:
            break
        sleep_s = interval_minutes * 60
        log.info("Sover %d min til neste sjekk (%s)",
                 interval_minutes,
                 datetime.utcnow().isoformat(timespec="seconds") + "Z")
        # Sov i små intervaller så signal-håndtering virker raskt
        slept = 0
        while slept < sleep_s and not stopping["flag"]:
            time.sleep(min(5, sleep_s - slept))
            slept += 5
    log.info("Watcher avsluttet")
    return 0


def cmd_status() -> int:
    from alerts import recent_alerts

    print(f"Config:")
    print(f"  Routes:                 {len(config.ROUTES)}")
    print(f"  Cabin:                  {config.CABIN}")
    print(f"  Window:                 {config.START_DATE} → {config.END_DATE}")
    print(f"  Min seats:              {config.MIN_SEATS}")
    print(f"  seats.aero key:         {'present' if config.SEATS_AERO_KEY else 'MISSING (fallback only)'}")
    print(f"  SMTP:                   {'configured' if config.SMTP_HOST else 'NOT configured'}")
    print(f"  Alert recipients:       {config.ALERT_EMAIL or '—'}")
    print()

    if config.LAST_RUN_PATH.exists():
        last = json.loads(config.LAST_RUN_PATH.read_text())
        print(f"Siste kjøring: {last.get('finished')}")
        print(f"  Primary: {last.get('primary_count')}  Fallback: {last.get('fallback_count')}  Matching: {len(last.get('matching', []))}")
        for f in last.get("matching", [])[:10]:
            seats = f.get("seats") or "?"
            print(f"    {f['origin']}→{f['destination']}  {f['date']}  seats={seats}  src={f['source']}")
        if len(last.get("matching", [])) > 10:
            print(f"    … og {len(last['matching']) - 10} til")
    else:
        print("Ingen tidligere kjøring funnet — kjør 'python run.py check'")
    print()

    alerts = recent_alerts(10)
    print(f"Siste {len(alerts)} alerts:")
    for a in alerts:
        print(f"  {a['sent_at']}  {a['subject']}")
    return 0


def cmd_dashboard() -> int:
    from dashboard import render
    path = render()
    print(f"Dashboard: {path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="SAS EuroBonus Award Monitor")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Kjør én enkelt sjekk")
    w = sub.add_parser("watch", help="Kjør som daemon")
    w.add_argument("--interval", type=int, default=360, help="Minutter mellom sjekker (default 360 = 6 timer)")
    sub.add_parser("status", help="Vis siste funn og cache")
    sub.add_parser("dashboard", help="Regenerer dashboard.html")

    args = p.parse_args()
    setup_logging(args.verbose)

    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "watch":
        return cmd_watch(args.interval)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "dashboard":
        return cmd_dashboard()
    return 1


if __name__ == "__main__":
    sys.exit(main())
