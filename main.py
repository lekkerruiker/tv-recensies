import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime

# 1. Config
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    print("❌ FOUT: Mis gegevens in GitHub Secrets.")
    sys.exit(1)

resend.api_key = API_KEY

# De bronnen die we scannen
SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/televisie",
    "Trouw": "https://www.trouw.nl/cultuur-media",
    "Parool": "https://www.parool.nl/columns-opinie",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media"
}

def get_reviews():
    print("🔍 Sniper-Scraper gestart...")
    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for name, url in SOURCES.items():
        try:
            print(f"Checking {name}...")
            response = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            found_count = 0
            for link in links:
                href = link['href']
                text = link.get_text().strip().lower()
                
                # Per krant specifieke logica
                is_match = False
                if name == "NRC" and ("zap" in text or "/nieuws/2026/" in href): # NRC gebruikt datum in URL
                    is_match = True
                elif name == "Volkskrant" and "tv-recensie" in text:
                    is_match = True
                elif name == "Trouw" and "blik van bos" in text:
                    is_match = True
                elif name == "Parool" and "han lips" in text:
                    is_match = True
                elif name == "Telegraaf" and "marcel peereboom voller" in text:
                    is_match = True

                if is_match:
                    # URL fixen
                    full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href}"
                    if "telegraaf" in name.lower() and not full_url.startswith('http'): 
                        full_url = "https://www.telegraaf.nl" + href

                    # Dubbelingen voorkomen
                    if any(full_url in r for r in results): continue
                    
                    archive_link = f"https://archive.is/{full_url}"
                    clean_title = text.replace('\n', ' ').strip()[:100] # Max 100 tekens
                    results.append(f"<li><strong>[{name}]</strong>: {clean_title.capitalize()}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
                    found_count += 1
                
                if found_count >= 2: break # We willen de mail niet te lang maken
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        print("Niets nieuws gevonden.")
        content = "<li>Geen specifieke media-recensies gevonden in de rubrieken vandaag.</li>"

    html_body = f"""
    <html>
        <body style='font-family: Arial, sans-serif; max-width: 600px; margin: auto;'>
            <h2 style='color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV Recensies van Vandaag</h2>
            <ul style='list-style: none; padding: 0;'>
                {content}
            </ul>
            <p style='font-size: 0.8em; color: #95a5a6; margin-top: 20px;'>Gegenereerd op {datetime.now().strftime('%d-%m-%Y %H:%M')}</p>
        </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"Media Update: {datetime.now().strftime('%d %b')}",
            "html": html_body,
        })
        print("✅ Mail verzonden!")
    except Exception as e:
        print(f"❌ Mail fout: {e}")

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
