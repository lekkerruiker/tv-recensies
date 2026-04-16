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
    print("❌ FOUT: Mis gegevens in Secrets.")
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
    debug_info = ""
    # Nog zwaardere vermomming
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
    }
    
    for name, url in SOURCES.items():
        try:
            print(f"--- {name} ---")
            resp = requests.get(url, headers=headers, timeout=15)
            status = resp.status_code
            print(f"Status: {status}")
            debug_info += f"{name}: Status {status}<br>"
            
            if status == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                links = soup.find_all('a', href=True)
                print(f"Links gevonden: {len(links)}")
                
                for link in links:
                    href = link['href'].lower()
                    text = link.get_text(strip=True)
                    
                    # Ultre-brede match
                    is_match = False
                    if name == "NRC" and ("zap" in href or "/2026/" in href): is_match = True
                    if name == "Volkskrant" and ("televisie" in href or "recensie" in href.lower()): is_match = True
                    if name == "Trouw" and ("bos" in href or "media" in href): is_match = True
                    if name == "Parool" and ("lips" in href or "kijkt-tv" in href): is_match = True
                    if name == "Telegraaf" and ("marcel" in href or "media" in href): is_match = True

                    if is_match and len(text) > 8:
                        full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href.lstrip('/')}"
                        if full_url not in [r[1] for r in results]:
                            results.append((name, full_url, text))
            else:
                debug_info += f"  (Blokkade bij {name}!)<br>"
        except Exception as e:
            print(f"Fout: {e}")
            debug_info += f"{name}: Fout {str(e)[:50]}<br>"
            
    # Mail content opbouwen
    html = ""
    if results:
        for r_name, r_url, r_text in results[:20]:
            archive = f"https://archive.is/{r_url}"
            html += f"<li><strong>[{r_name}]</strong> {r_text}<br><a href='{archive}'>Lees via Archive</a></li><br>"
    else:
        html = f"<li>Niets gevonden.</li><p>Debug Log:<br>{debug_info}</p>"
    
    return html

def send_mail(content):
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Debug Update: {datetime.now().strftime('%H:%M')}",
        "html": f"<html><body><h3>Resultaten:</h3><ul>{content}</ul></body></html>"
    })

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
