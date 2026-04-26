"""Konfigurasjon for SAS EuroBonus Award Monitor."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Destinasjoner lastes fra destinations.yaml ---
import destinations as _dests   # noqa: E402

DESTINATIONS = _dests.load()
ROUTES: list[tuple[str, str]] = _dests.all_routes(skip_manual=True)

# Set for fallback/AwardFares-filter
ORIGIN_AIRPORTS: set[str] = set()
TARGET_DESTINATIONS: set[str] = set()
for _d in DESTINATIONS:
    ORIGIN_AIRPORTS.update(_d.origin_priority)
    TARGET_DESTINATIONS.update(_d.airports)

# Bredeste søkevindu fra alle destinasjoner
START_DATE = min((d.window_start for d in DESTINATIONS), default="2026-07-01")
END_DATE = max((d.window_end for d in DESTINATIONS), default="2027-12-31")
MIN_SEATS = min((d.min_seats for d in DESTINATIONS), default=2)
CABIN = "business"
PROGRAM = "eurobonus"

# --- Filer ---
CACHE_DIR = BASE_DIR / "cache"
LOGS_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
DB_PATH = CACHE_DIR / "seen.db"
LOG_PATH = LOGS_DIR / "monitor.log"
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"
LAST_RUN_PATH = CACHE_DIR / "last_run.json"

for _d in (CACHE_DIR, LOGS_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- API/SMTP ---
SEATS_AERO_KEY = os.getenv("SEATS_AERO_KEY", "").strip()
SEATS_AERO_URL = "https://seats.aero/partnerapi/availability"

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
ALERT_EMAIL = [e.strip() for e in os.getenv("ALERT_EMAIL", "").split(",") if e.strip()]
DEDUP_WINDOW_DAYS = int(os.getenv("DEDUP_WINDOW_DAYS", "30"))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
