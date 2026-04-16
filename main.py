import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime

API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

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
    debug_log = ""
    
    # Extreem menselijke headers
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.nl/',
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1'
    }

    for name, url in SOURCES.items():
        try:
            # We voegen een kleine random vertraging toe aan de request (vibe check)
            resp = session.get(url, headers=headers, timeout=20)
            debug_log += f"{name}: {resp.status_code}<br>"
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Zoek naar alles wat op een link lijkt met media termen
                for link in soup.find_all('a', href=True):
                    href = link['href'].lower()
                    text = link.get_text(strip=True)
                    
                    keywords = ['lips', 'zap', 'bos', 'peereboom', 'televisie', 'recensie', 'kijkt-tv']
                    if any(k in href or k in text.lower() for k in keywords):
                        full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href.lstrip('/')}"
                        if len(text) > 10 and full_url not in [r[1] for r in results]:
                            results.append((name, full_url, text))
        except Exception as e:
            debug_log += f"{name}: Fout {str(e)[:30]}<br>"

    html = ""
    if results:
        for r_name, r_url, r_text in results[:15]:
            archive = f"https://archive.is/{r_url}"
            html += f"<li><strong>[{r_name}]</strong> {r_text}<br><a href='{archive}'>Lees via Archive</a></li><br>"
    else:
        html = f"<li>Nog steeds blokkades. Debug: {debug_log}</li>"
    return html

def send_mail(content):
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update Debug: {datetime.now().strftime('%H:%M')}",
        "html": f"<html><body><h3>Status Update:</h3><ul>{content}</ul></body></html>"
    })

if __name__ == "__main__":
    send_mail(get_reviews())
