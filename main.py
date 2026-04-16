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
    print("❌ FOUT: Mis gegevens in GitHub Secrets.")
    sys.exit(1)

resend.api_key = API_KEY

# De meest simpele trefwoorden in de URL
KEYWORDS = ["lips", "zap", "bos", "peereboom", "televisie", "recensie", "kijkt-tv"]

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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
    }
    
    for name, url in SOURCES.items():
        try:
            print(f"--- Scannen: {name} ---")
            response = requests.get(url, headers=headers, timeout=20)
            print(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ {name} blokkeert ons (Status {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link['href'].lower()
                text = link.get_text(strip=True)
                
                # Als een van de keywords in de URL staat, is het waarschijnlijk raak
                if any(key in href for key in KEYWORDS):
                    # URL compleet maken
                    full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href}"
                    if "telegraaf" in name.lower() and not full_url.startswith('http'):
                        full_url = "https://www.telegraaf.nl" + href

                    # Alleen links met een beetje tekst (geen icoontjes)
                    if len(text) < 8:
                        continue
                        
                    if any(full_url in r for r in results):
                        continue
                    
                    archive_link = f"https://archive.is/{full_url}"
                    results.append(f"<li><strong>[{name}]</strong>: {text}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
            
            print(f"Gevonden bij {name}: {len(results)}")
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen links gevonden. Check de GitHub Logs voor statuscodes (403 = blokkade).</li>"

    html_body = f"<html><body style='font-family:sans-serif;'><h2>📺 TV Recensies Update</h2><ul>{content}</ul></body></html>"
    
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m-%Y')}",
        "html": html_body,
    })

if __name__ == "__main__":
    review_html = get_reviews()
    send_mail(review_html)
