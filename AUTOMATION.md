# Automasjon — slik kjører du sjekken hands-off

Du har 4 valg, fra enkleste til mest robuste:

## A) Lokal: launchd (Mac)
**For:** Du har Mac-en din på til vanlig
**Mot:** Stopper hvis Mac sover eller du er bortreist

```bash
cp "com.jonasbech.sasmonitor.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.jonasbech.sasmonitor.plist
launchctl list | grep sasmonitor    # bekreft
```
Kjører kl 07:00 / 13:00 / 19:00 hver dag. Logger til `logs/launchd.*.log`.

Stop:
```bash
launchctl unload ~/Library/LaunchAgents/com.jonasbech.sasmonitor.plist
```

---

## B) Sky-cron: GitHub Actions (anbefalt — gratis + uavhengig av Mac)

### Steg 1: Push til privat GitHub-repo
```bash
cd "Projects/SAS EuroBonus Monitor"
git init
git add .
git commit -m "init: SAS EuroBonus monitor"
gh repo create sas-eurobonus-monitor --private --source=. --push
```

### Steg 2: Legg secrets i repoet
GitHub → Settings → Secrets and variables → Actions → "New repository secret"

Legg inn:

| Navn | Verdi |
|---|---|
| `SEATS_AERO_KEY` | `pro_3CuPXqdjD90baSLPA1IFH7QUQOO` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `jonas@villoid.com` |
| `SMTP_PASS` | Gmail App Password (myaccount.google.com → Security → 2-Step → App passwords) |
| `SMTP_FROM` | `jonas@villoid.com` |
| `ALERT_EMAIL` | `jonas@villoid.com` |

### Steg 3: Aktiver workflowen
Workflowen `.github/workflows/check.yml` er allerede skrevet. Den vil:
- Kjøre **hver 6. time** (cron `5 */6 * * *`)
- Kalle `python run.py check`
- Sende e-post-alert ved nye seter (via SMTP)
- Committe `cache/seen.db` tilbake til repo for dedup på tvers av kjøringer
- Laste opp dashboardet som artifact (lastes ned fra Actions-tab)

Trigger første kjøring manuelt: GitHub → Actions → "SAS EuroBonus Check" → "Run workflow"

### Costs
GitHub Actions for **private repos**: 2 000 minutter/mnd gratis. Vår sjekk tar ~1 min × 4 ganger/dag × 30 dager = 120 min/mnd. **Gratis.**

---

## C) Claude Code remote agent (`/schedule`)

Krever ingenting fra deg utover at SMTP er satt opp i lokal `.env`.
Si til Claude:
> "/schedule kjør 'python run.py check' hver 6. time"

Kjører på Anthropic infra. Også gratis.

---

## D) Lokal docker / cron

Hvis du kjører en server hjemme eller på en VPS:

```cron
5 */6 * * * cd /path/to/sas-monitor && /path/to/.venv/bin/python run.py check
```

---

## Varsling — hvilken kanal

`alerts.py` støtter SMTP (Gmail/iCloud/etc) ut av boksen. Andre kanaler:

### Slack-webhook (5 min å sette opp)
Lag en webhook på api.slack.com/apps → Incoming Webhooks. Lim inn URL i `.env`:
```
SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
```
Si fra hvis du vil ha det — jeg legger til SLack-poster i `alerts.py` (~30 linjer).

### Telegram-bot
Snakk med @BotFather → få token. Si fra så bygger jeg.

### Pushover (push til mobil)
~$5 engangsavgift, ekstremt pålitelig.

---

## Phantom availability — viktig

Selv med fersk seats.aero-data kan SAS-seter være borte når du klikker.
Dashboard markerer:
- 🟢 grønn `Last seen <12t` — fersk
- 🟡 gul `stale 12-24t` — verifiser
- 🔴 rød `gammel >24t` — vis kun manuelt sjekk

**Klikk alltid "Book direkte på SAS" først** før du blir glad. SAS-bookingen er den eneste sannheten.
