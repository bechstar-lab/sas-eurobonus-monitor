"""
Alert-system: dedupliser nye flights og send e-post.
SQLite-basert seen-cache med tidsstempel + utløp.
"""
from __future__ import annotations

import logging
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

import config
from monitor import Flight

log = logging.getLogger("alerts")


# --------------------------------------------------------------------------- #
# Seen-cache
# --------------------------------------------------------------------------- #

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH)
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            key TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL,
            last_alerted TEXT,
            payload TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT NOT NULL,
            subject TEXT,
            body_summary TEXT
        )
    """)
    return c


def filter_new(flights: list[Flight]) -> list[Flight]:
    """Returner kun flights vi ikke har varslet om innen DEDUP_WINDOW_DAYS."""
    if not flights:
        return []
    threshold = (datetime.utcnow() - timedelta(days=config.DEDUP_WINDOW_DAYS)).isoformat()
    new: list[Flight] = []
    with _conn() as c:
        for f in flights:
            row = c.execute(
                "SELECT last_alerted FROM seen WHERE key = ?", (f.key,)
            ).fetchone()
            if row is None:
                new.append(f)
            else:
                last_alerted = row[0]
                if last_alerted is None or last_alerted < threshold:
                    new.append(f)
    return new


def mark_alerted(flights: list[Flight]) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        for f in flights:
            c.execute("""
                INSERT INTO seen (key, first_seen, last_alerted, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET last_alerted = excluded.last_alerted
            """, (f.key, now, now, repr(f.to_dict())))


def log_alert(subject: str, summary: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO alerts_log (sent_at, subject, body_summary) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(timespec="seconds"), subject, summary),
        )


def recent_alerts(limit: int = 10) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT sent_at, subject, body_summary FROM alerts_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"sent_at": r[0], "subject": r[1], "summary": r[2]} for r in rows]


# --------------------------------------------------------------------------- #
# Lenker
# --------------------------------------------------------------------------- #

def sas_booking_link(f: Flight) -> str:
    params = {
        "bookingFlow": "BONUS",
        "from": f.origin,
        "to": f.destination,
        "outDate": f.date if f.date and f.date != "?" else "",
        "adt": 2, "chd": 0, "inf": 0,
    }
    return "https://www.flysas.com/en/book/flights/?" + urlencode(params)


def awardfares_link(f: Flight) -> str:
    params = {
        "origin": f"{f.origin}.",
        "destination": f"{f.destination}.",
        "cabin": "C",
        "program": "EuroBonus",
    }
    return "https://awardfares.com/search?" + urlencode(params)


# --------------------------------------------------------------------------- #
# E-post
# --------------------------------------------------------------------------- #

def _format_flight_block(f: Flight) -> str:
    seats = f"{f.seats}+ seter" if f.seats else "Seter ukjent (sjekk lenke)"
    cost = f" — {f.mileage_cost:,} pts".replace(",", " ") if f.mileage_cost else ""
    airline = f" • {f.airline}" if f.airline else ""
    stops = f" • {f.stops}" if f.stops else ""
    return (
        f"{f.origin} → {f.destination}  {f.date}\n"
        f"  {seats}{cost}{airline}{stops}\n"
        f"  Kilde: {f.source}\n"
        f"  SAS: {sas_booking_link(f)}\n"
        f"  AwardFares: {awardfares_link(f)}\n"
    )


def _format_flight_html(f: Flight) -> str:
    seats = f"{f.seats}+ seter" if f.seats else "Seter ukjent"
    cost = f" — {f.mileage_cost:,} pts".replace(",", " ") if f.mileage_cost else ""
    airline = f" · {f.airline}" if f.airline else ""
    stops = f" · {f.stops}" if f.stops else ""
    return f"""
    <div style="margin:18px 0;padding:14px 16px;border:1px solid #e5ddd0;border-radius:8px;background:#fff;">
      <div style="font:600 17px Georgia,serif;color:#5C4B3A;">
        {f.origin} → {f.destination} <span style="color:#8a7a66;font-weight:400;"> {f.date}</span>
      </div>
      <div style="font:400 14px Georgia,serif;color:#5C4B3A;margin-top:4px;">
        {seats}{cost}{airline}{stops} · <em>{f.source}</em>
      </div>
      <div style="margin-top:10px;font:400 13px -apple-system,sans-serif;">
        <a href="{sas_booking_link(f)}" style="color:#5C4B3A;margin-right:14px;">Book på SAS →</a>
        <a href="{awardfares_link(f)}" style="color:#5C4B3A;">Sjekk i AwardFares →</a>
      </div>
    </div>
    """


def send_alert(flights: list[Flight]) -> bool:
    """Send én samle-mail med alle nye flights. Returner True ved suksess."""
    if not flights:
        return False
    if not (config.SMTP_HOST and config.SMTP_USER and config.ALERT_EMAIL):
        log.warning("SMTP ikke konfigurert — hopper over e-post (%d nye flights)", len(flights))
        return False

    routes = sorted({f"{f.origin}-{f.destination}" for f in flights})
    subject = f"[EuroBonus] {len(flights)} nye award-seter: {', '.join(routes[:4])}"
    if len(routes) > 4:
        subject += f" +{len(routes) - 4}"

    text_body = "Nye SAS EuroBonus award-seter funnet:\n\n" + "\n".join(
        _format_flight_block(f) for f in flights
    )
    html_body = f"""
    <html><body style="background:#FAF7F2;padding:24px;font-family:Georgia,serif;color:#5C4B3A;">
      <h1 style="font-weight:600;font-size:22px;margin:0 0 6px 0;">Nye award-seter</h1>
      <p style="margin:0 0 18px 0;color:#8a7a66;font-size:14px;">
        {len(flights)} nye flights matcher dine ruter.
      </p>
      {''.join(_format_flight_html(f) for f in flights)}
      <p style="margin-top:24px;font-size:12px;color:#8a7a66;">
        Generert {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
      </p>
    </body></html>
    """

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = ", ".join(config.ALERT_EMAIL)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(msg)
    except Exception:
        log.exception("SMTP send feilet")
        return False

    log.info("Sendte alert med %d flights til %s", len(flights), config.ALERT_EMAIL)
    log_alert(subject, f"{len(flights)} flights: {', '.join(routes)}")
    return True


def process(flights: list[Flight]) -> dict:
    """Filtrer, send, marker. Returnerer rapport."""
    new = filter_new(flights)
    sent = send_alert(new) if new else False
    if sent:
        mark_alerted(new)
    elif new and not config.SMTP_HOST:
        # Ingen SMTP — marker likevel som sett så vi ikke spammer kommende kjøringer
        # når brukeren har valgt å ikke konfigurere e-post
        mark_alerted(new)
    return {
        "candidates": len(flights),
        "new": len(new),
        "sent": sent,
        "new_flights": [f.to_dict() for f in new],
    }
