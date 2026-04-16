"""
Dagelijkse TV-recensie mailer — RSS-versie
Leest RSS-feeds van 5 kranten, filtert op TV/televisie-artikelen
van vandaag, maakt archive.ph-links en stuurt een HTML-digest via Resend.

Vereiste omgevingsvariabelen (GitHub Secrets):
  RESEND_API_KEY   — je Resend API-sleutel
  MAIL_TO          — ontvanger
  MAIL_FROM        — afzender (zelfde als MAIL_TO voor gratis Resend-tier)
"""

import os
import re
import time
import datetime
import xml.etree.ElementTree as ET
import requests

# ---------------------------------------------------------------------------
# RSS-feeds per krant + zoekwoorden om TV-artikelen te herkennen
# ---------------------------------------------------------------------------
KRANTEN = [
    {
        "naam": "Volkskrant",
        "rss_url": "https://www.volkskrant.nl/voorpagina/rss",
        "tv_termen": ["televisie", "tv-recensie", "kijktip", "serie", "documentaire"],
    },
    {
        "naam": "AD",
        "rss_url": "https://www.ad.nl/home/rss.xml",
        "tv_termen": ["televisie", "tv-recensie", "kijktip", "serie", "documentaire"],
    },
    {
        "naam": "NRC",
        "rss_url": "https://www.nrc.nl/rss/",
        "tv_termen": ["televisie", "tv-recensie", "kijktip", "serie", "documentaire"],
    },
    {
        "naam": "Trouw",
        "rss_url": "https://www.trouw.nl/voorpagina/rss.xml",
        "tv_termen": ["televisie", "tv-recensie", "kijktip", "serie", "documentaire"],
    },
    {
        "naam": "Telegraaf",
        "rss_url": "https://www.telegraaf.nl/rss",
        "tv_termen": ["televisie", "tv-recensie", "kijktip", "serie", "documentaire"],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TV-recensie-bot/1.0; +https://github.com)"
    )
}

ARCHIVE_SUBMIT = "https://archive.ph/submit/"
ARCHIVE_BASE   = "https://archive.ph/"


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def haal_rss(url: str) -> list[dict]:
    """Haal RSS-feed op en geef lijst van artikelen terug."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  RSS-fout: {e}")
        return []

    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        print(f"  XML-parseerfout: {e}")
        return []

    artikelen = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for item in items:
        titel = (
            getattr(item.find("title"), "text", "") or
            getattr(item.find("atom:title", ns), "text", "") or ""
        )
        link = (
            getattr(item.find("link"), "text", "") or
            (item.find("atom:link", ns) or ET.Element("x")).get("href", "") or ""
        )
        beschrijving = (
            getattr(item.find("description"), "text", "") or
            getattr(item.find("atom:summary", ns), "text", "") or ""
        )
        artikelen.append({
            "titel": titel.strip(),
            "link": link.strip(),
            "beschrijving": (beschrijving or "").strip(),
        })

    return artikelen


def is_tv_artikel(artikel: dict, tv_termen: list[str]) -> bool:
    """Controleer of een artikel over TV gaat op basis van trefwoorden."""
    tekst = (artikel["titel"] + " " + artikel["beschrijving"]).lower()
    return any(term in tekst for term in tv_termen)


def zoek_tv_artikel(krant: dict) -> dict | None:
    """Zoek het eerste TV-artikel in de RSS-feed van een krant."""
    print(f"[{krant['naam']}] RSS ophalen...")
    artikelen = haal_rss(krant["rss_url"])

    if not artikelen:
        print(f"  -> Geen artikelen gevonden in RSS.")
        return None

    print(f"  -> {len(artikelen)} artikelen in feed.")

    for artikel in artikelen:
        if is_tv_artikel(artikel, krant["tv_termen"]):
            print(f"  -> TV-artikel gevonden: {artikel['titel'][:60]}")
            return artikel

    print(f"  -> Geen TV-artikel gevonden, eerste artikel als fallback.")
    return artikelen[0] if artikelen else None


def archiveer(url: str) -> str:
    """Archiveer URL via archive.ph en retourneer de archive-link."""
    try:
        resp = requests.post(
            ARCHIVE_SUBMIT,
            data={"url": url},
            headers=HEADERS,
            timeout=60,
            allow_redirects=True,
        )
        if ARCHIVE_BASE in resp.url and resp.url != ARCHIVE_SUBMIT:
            return resp.url

        refresh = resp.headers.get("Refresh", "")
        match = re.search(r"url=(https://archive\.ph/\S+)", refresh, re.I)
        if match:
            return match.group(1)

    except Exception as e:
        print(f"  archive.ph fout: {e}")

    return f"https://archive.ph/newest/{url}"


def bouw_html_email(resultaten: list[dict], datum: str) -> str:
    """Genereer de HTML-body van de e-mail."""
    rijen = ""
    for item in resultaten:
        link = item.get("archive_url") or item.get("artikel_url") or "#"
        titel = item.get("titel", item["naam"])[:80]
        heeft_link = link != "#"

        artikel_cel = (
            f'<a href="{link}" style="color:#1a6fa8;text-decoration:none;">{titel}</a>'
            if heeft_link else titel
        )

        rijen += f"""
        <tr>
          <td style="padding:14px 16px;font-weight:600;font-size:14px;
                     border-bottom:1px solid #eee;width:110px;vertical-align:top;">
            {item["naam"]}
          </td>
          <td style="padding:14px 16px;font-size:14px;border-bottom:1px solid #eee;
                     line-height:1.5;">
            {artikel_cel}
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="nl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:24px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;
                    box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden;">
        <tr>
          <td style="background:#1a1a2e;padding:24px 32px;">
            <p style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">
              TV-recensies
            </p>
            <p style="margin:6px 0 0;color:#aab4c8;font-size:13px;">{datum}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 16px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {rijen}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px;background:#f9f9f9;
                     border-top:1px solid #eee;font-size:11px;color:#999;">
            Links gaan via archive.ph om paywall te omzeilen
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def verstuur_via_resend(html_body: str, datum: str) -> bool:
    """Verstuur de e-mail via de Resend API."""
    api_key   = os.environ["RESEND_API_KEY"]
    mail_to   = os.environ["MAIL_TO"]
    mail_from = os.environ["MAIL_FROM"]

    payload = {
        "from": mail_from,
        "to": [mail_to],
        "subject": f"TV-recensies {datum}",
        "html": html_body,
    }

    resp = requests.post(
        "https://api.resend.com/emails",
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )

    if resp.status_code in (200, 201):
        print(f"E-mail verstuurd naar {mail_to}.")
        return True
    else:
        print(f"Resend fout {resp.status_code}: {resp.text}")
        return False


# ---------------------------------------------------------------------------
# Hoofdprogramma
# ---------------------------------------------------------------------------

def main():
    vandaag = datetime.date.today().strftime("%-d %B %Y")
    print(f"=== TV-recensie mailer - {vandaag} ===\n")

    resultaten = []

    for krant in KRANTEN:
        artikel = zoek_tv_artikel(krant)

        archive_url = None
        artikel_url = None
        titel = krant["naam"]

        if artikel:
            artikel_url = artikel["link"]
            titel = artikel["titel"]
            if artikel_url:
                print(f"  -> Archiveren...")
                archive_url = archiveer(artikel_url)
                print(f"  -> Archive: {archive_url}")
                time.sleep(3)

        resultaten.append({
            "naam": krant["naam"],
            "titel": titel,
            "artikel_url": artikel_url,
            "archive_url": archive_url,
        })
        print()

    print("E-mail samenstellen en versturen...")
    html = bouw_html_email(resultaten, vandaag)
    verstuur_via_resend(html, vandaag)


if __name__ == "__main__":
    main()
