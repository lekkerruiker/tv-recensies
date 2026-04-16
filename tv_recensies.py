"""
Dagelijkse TV-recensie mailer
Scrapet de TV-rubriek van 5 Nederlandse kranten,
maakt archive.is-links en stuurt een HTML-digest via Resend.

Vereiste omgevingsvariabelen (stel in als GitHub Secrets):
  RESEND_API_KEY   — je Resend API-sleutel
  MAIL_TO          — ontvanger, bijv. jij@example.com
  MAIL_FROM        — afzender, bijv. nieuws@jouwdomein.com
                     (moet verified zijn in Resend)
"""

import os
import re
import time
import datetime
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuratie per krant
# ---------------------------------------------------------------------------
# Elke krant heeft een sectie-URL. Het script pakt de eerste link op die pagina
# die eruitziet als een TV-recensie of kijktip van vandaag.
# Pas de selectors aan als een krant zijn HTML-structuur wijzigt.

KRANTEN = [
    {
        "naam": "Volkskrant",
        "sectie_url": "https://www.volkskrant.nl/televisie",
        "artikel_patroon": r"/televisie/",          # URL moet dit bevatten
        "css_selector": "a[href*='/televisie/']",
    },
    {
        "naam": "AD",
        "sectie_url": "https://www.ad.nl/tv",
        "artikel_patroon": r"/tv/",
        "css_selector": "a[href*='/tv/']",
    },
    {
        "naam": "NRC",
        "sectie_url": "https://www.nrc.nl/rubriek/televisie/",
        "artikel_patroon": r"/nieuws/",
        "css_selector": "article a, h2 a, h3 a",
    },
    {
        "naam": "Trouw",
        "sectie_url": "https://www.trouw.nl/tv-film",
        "artikel_patroon": r"/tv-film/",
        "css_selector": "a[href*='/tv-film/']",
    },
    {
        "naam": "Telegraaf",
        "sectie_url": "https://www.telegraaf.nl/entertainment/tv",
        "artikel_patroon": r"/entertainment/",
        "css_selector": "a[href*='/entertainment/']",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

ARCHIVE_SUBMIT = "https://archive.ph/submit/"
ARCHIVE_BASE   = "https://archive.ph/"


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def haal_eerste_artikel_url(krant: dict) -> str | None:
    """Haal de URL van het eerste (meest recente) TV-artikel op."""
    try:
        r = requests.get(krant["sectie_url"], headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[{krant['naam']}] Fout bij ophalen sectie: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    patroon = re.compile(krant["artikel_patroon"])

    for tag in soup.select(krant["css_selector"]):
        href = tag.get("href", "")
        # Maak relatieve URLs absoluut
        if href.startswith("/"):
            basis = "/".join(krant["sectie_url"].split("/")[:3])
            href = basis + href
        if patroon.search(href) and len(href) > 40:
            return href

    print(f"[{krant['naam']}] Geen artikellink gevonden.")
    return None


def archiveer(url: str) -> str:
    """
    Dien de URL in bij archive.ph en retourneer de archive-link.
    Archive.ph reageert met een redirect naar de gearchiveerde pagina.
    Als het archiveren mislukt, geef de originele URL terug.
    """
    try:
        resp = requests.post(
            ARCHIVE_SUBMIT,
            data={"url": url},
            headers=HEADERS,
            timeout=60,
            allow_redirects=True,
        )
        # De uiteindelijke URL na redirects is de archive-link
        if ARCHIVE_BASE in resp.url and resp.url != ARCHIVE_SUBMIT:
            return resp.url

        # Sommige versies sturen de archive-URL in een Refresh-header
        refresh = resp.headers.get("Refresh", "")
        match = re.search(r"url=(https://archive\.ph/\S+)", refresh, re.I)
        if match:
            return match.group(1)

    except Exception as e:
        print(f"  archive.ph fout voor {url}: {e}")

    # Fallback: gebruik archive.ph/newest/ (toont recentste archief als het bestaat)
    return f"https://archive.ph/newest/{url}"


def bouw_html_email(resultaten: list[dict], datum: str) -> str:
    """Genereer de HTML-body van de e-mail."""
    rijen = ""
    for item in resultaten:
        status_kleur = "#2d6a4f" if item["archive_url"] else "#c0392b"
        status_tekst = "✓ gearchiveerd" if item["archive_url"] else "✗ niet gevonden"
        link = item["archive_url"] or item["artikel_url"] or "#"
        artikel_tekst = (
            f'<a href="{link}" style="color:#1a6fa8;text-decoration:none;">'
            f'{item["naam"]}</a>'
            if link != "#"
            else item["naam"]
        )
        rijen += f"""
        <tr>
          <td style="padding:14px 16px;font-weight:600;font-size:15px;
                     border-bottom:1px solid #eee;width:120px;">
            {item["naam"]}
          </td>
          <td style="padding:14px 16px;font-size:14px;border-bottom:1px solid #eee;">
            {artikel_tekst}
          </td>
          <td style="padding:14px 16px;font-size:12px;color:{status_kleur};
                     border-bottom:1px solid #eee;white-space:nowrap;">
            {status_tekst}
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="nl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;
                    box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden;">
        <!-- Header -->
        <tr>
          <td style="background:#1a1a2e;padding:24px 32px;">
            <p style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">
              📺 TV-recensies
            </p>
            <p style="margin:6px 0 0;color:#aab4c8;font-size:13px;">{datum}</p>
          </td>
        </tr>
        <!-- Artikelen -->
        <tr>
          <td style="padding:0 16px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {rijen}
            </table>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px;background:#f9f9f9;
                     border-top:1px solid #eee;font-size:11px;color:#999;">
            Automatisch gegenereerd · archive.ph links omzeilen paywall
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def verstuur_via_resend(html_body: str, datum: str) -> bool:
    """Verstuur de e-mail via de Resend API."""
    api_key  = os.environ["RESEND_API_KEY"]
    mail_to  = os.environ["MAIL_TO"]
    mail_from = os.environ.get("MAIL_FROM", "tv@resend.dev")  # resend.dev domein werkt zonder verificatie voor testen

    payload = {
        "from": mail_from,
        "to": [mail_to],
        "subject": f"📺 TV-recensies {datum}",
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
    print(f"=== TV-recensie mailer — {vandaag} ===\n")

    resultaten = []

    for krant in KRANTEN:
        print(f"[{krant['naam']}] Sectie ophalen…")
        artikel_url = haal_eerste_artikel_url(krant)

        archive_url = None
        if artikel_url:
            print(f"  → Artikel: {artikel_url}")
            print(f"  → Archiveren bij archive.ph…")
            archive_url = archiveer(artikel_url)
            print(f"  → Archive: {archive_url}")
            time.sleep(3)  # Wees beleefd voor archive.ph
        else:
            print(f"  → Geen artikel gevonden, wordt overgeslagen.")

        resultaten.append({
            "naam": krant["naam"],
            "artikel_url": artikel_url,
            "archive_url": archive_url,
        })

    print("\nE-mail samenstellen…")
    html = bouw_html_email(resultaten, vandaag)

    print("Versturen via Resend…")
    verstuur_via_resend(html, vandaag)


if __name__ == "__main__":
    main()
