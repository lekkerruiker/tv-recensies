import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime

# 1. Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    print("❌ FOUT: Mis gegevens.")
    sys.exit(1)

resend.api_key = API_KEY

SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/televisie",
    "Trouw": "https://www.trouw.nl/cultuur-media",
    "Parool": "https://www.parool.nl/columns-opinie",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media"
}

def get_reviews():
    results = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    for name, url in SOURCES.items():
        try:
            print(f"--- {name} ---")
            resp = requests.get(url, headers=headers, timeout=15)
            print(f"Status: {resp.status_code}")
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            # We pakken ELKE link en kijken of er bekende patronen in zitten
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                text = link.get_text(strip=True)
                
                # Zeer brede filters gebaseerd op jouw voorbeelden
                match = False
                if name == "NRC" and ("/2026/" in href or "zap" in href): match = True
                if name == "Volkskrant" and ("~b" in href or "televisie" in href): match = True # VK gebruikt vaak ~b codes
                if name == "Trouw" and ("bos" in href or "cultuur-media" in href): match = True
                if name == "Parool" and ("lips" in href or "kijkt-tv" in href): match = True
                if name == "Telegraaf" and ("marcel" in href or "media" in href): match = True

                if match and len(text) > 10:
                    full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href}"
                    if "telegraaf" in name.lower() and not full_url.startswith('http'): full_url = "https://www.telegraaf.nl" + href
                    
                    if full_url not in [r[1] for r in results]: # Voorkom dubbelen
                        results.append((name, full_url, text))
            
            print(f"Gevonden: {len(results)}")
        except Exception as e:
            print(f"Fout: {e}")
            
    # Maak HTML van de resultaten
    html = ""
    for r_name, r_url, r_text in results[:15]: # Max 15 links totaal
        archive = f"https://archive.is/{r_url}"
        html += f"<li><strong>[{r_name}]</strong> {r_text}<br><a href='{archive}'>Lees via Archive</a></li><br>"
    return html

def send_mail(content):
    if not content:
        content = "<li>Helaas, nog steeds niets. Check de GitHub Logs voor de 'Status' codes per krant.</li>"

    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"<html><body><h3>Resultaten:</h3><ul>{content}</ul></body></html>"
    })

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
