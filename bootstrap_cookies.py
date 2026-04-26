"""
Engangs-bootstrap: åpner et synlig Chromium, lar deg løse Cloudflare-challenge
og evt. logge inn på AwardFares. Lagrer storage_state til
cache/awardfares_cookies.json som monitor.py automatisk gjenbruker.

Bruk:
  .venv/bin/python bootstrap_cookies.py

Når browseren åpner: vent til siden vises (challenge løses ofte automatisk).
Logg gjerne inn også for å få per-rute resultater. Trykk ENTER i terminalen
for å lagre og lukke.
"""
from __future__ import annotations

import sys

import config

URLS = [
    "https://awardfares.com/programs/sas-eurobonus",
]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright mangler. Kjør: .venv/bin/pip install playwright && "
              ".venv/bin/playwright install chromium")
        return 1

    out_path = config.CACHE_DIR / "awardfares_cookies.json"
    print(f"Åpner Chromium (synlig). Cookies lagres til:\n  {out_path}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent=config.USER_AGENT)
        page = ctx.new_page()
        for url in URLS:
            print(f" -> {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        print()
        print("Sjekk at Cloudflare-challenge er løst og siden viser flights.")
        print("Vil du logge inn på AwardFares også? Gjør det nå (gratis konto = mer data).")
        input("Trykk ENTER her for å lagre cookies og lukke...")
        ctx.storage_state(path=str(out_path))
        browser.close()

    print(f"\nOK — lagret. Test med:")
    print("  .venv/bin/python -c 'from monitor import check_awardfares; print(len(check_awardfares()))'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
