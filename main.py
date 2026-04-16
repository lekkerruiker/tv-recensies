import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime, timedelta

# 1. Config
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    print("❌ FOUT: Mis gegevens in GitHub Secrets.")
    sys.exit(1)

resend.api_key = API_KEY

# Datums van vandaag en gisteren voor URL-check
today_str = datetime.now().strftime("%Y/%m/%d")
yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")
short_today = datetime.now().strftime("%Y-%m-%d")
short_yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/televisie",
    "Trouw": "https://www.trouw.nl/cultuur-media",
    "Parool": "https://www.parool.nl/columns-opinie",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media"
}

def get_reviews():
    print(f"🔍 Scraper zoekt naar recensies van {short_today} en {short_yesterday}...")
    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for name, url in SOURCES.items():
        try:
            response = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            found_count = 0
            for link in links:
                href = link['href']
                text = link.get_text().strip().lower()
                
                # We checken of de tekst OF de URL een van onze trefwoorden bevat
                is_match = False
                
                # NRC: Check op 'zap' of datum van gisteren/vandaag in URL
                if name == "NRC":
                    if any(d in href for d in [today_str, yesterday_str]) or "zap" in text:
                        is_match = True
                
                # Volkskrant: 'tv-recensie'
                elif name == "Volkskrant":
                    if "tv-recensie" in text or "televisie" in href:
                        is_match = True
                
                # Trouw: 'blik van bos'
                elif name == "Trouw":
                    if "blik van bos" in text or "bos" in href:
                        is_match = True
                
                # Parool: 'han lips'
                elif name == "Parool":
                    if "han lips" in text or "han-lips" in href:
                        is_match = True
                
                # Telegraaf: 'marcel'
                elif name == "Telegraaf":
                    if "marcel" in text or "marcel-peereboom-voller" in href:
                        is_match = True

                if is_match:
                    full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href}"
                    if "telegraaf" in name.lower() and not full_url.startswith('http'): 
                        full_url = "https://www.telegraaf.nl" + href

                    if any(full_url in r for r in results): continue
                    
                    archive_link = f"https://archive.is/{full_url}"
                    display_text = text.capitalize() if len(text) > 5 else "Klik hier voor de recensie"
                    
                    results.append(f"<li><strong>[{name}]</strong>: {display_text}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
                    found_count += 1
                
                if found_count >= 3: break
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen recensies gevonden van vandaag of gisteren. De redacties zijn blijkbaar lui.</li>"

    html_body = f"""
    <html>
        <body style='font-family: Arial, sans-serif; max-width: 600px; margin: auto;'>
            <h2 style='color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV Recensies (Laatste 48u)</h2>
            <ul style='list-style: none; padding: 0;'>
                {content}
            </ul>
            <p style='font-size: 0.8em; color: #95a5a6; margin-top: 20px;'>Check van {short_today}</p>
        </body>
    </html>
    """
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d %b')}",
        "html": html_body,
    })

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
