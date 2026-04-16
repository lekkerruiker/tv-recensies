import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime, timedelta

# 1. Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    print("❌ FOUT: Mis gegevens in GitHub Secrets.")
    sys.exit(1)

resend.api_key = API_KEY

# Tijdvenster: we zoeken naar 2026/04/16 en 2026/04/15
today_path = datetime.now().strftime("%Y/%m/%d")
yesterday_path = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")

SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/televisie",
    "Trouw": "https://www.trouw.nl/cultuur-media",
    "Parool": "https://www.parool.nl/columns-opinie",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media"
}

def get_reviews():
    print(f"🔍 Scannen voor datums: {today_path} en {yesterday_path}")
    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for name, url in SOURCES.items():
        try:
            response = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            print(f"--- {name}: {len(links)} links gevonden ---")
            
            found_in_source = 0
            for link in links:
                href = link['href']
                # Pak de tekst uit de link of uit een kopje (h1-h4) in de link
                text_element = link.find(['h1', 'h2', 'h3', 'h4', 'span'])
                text = text_element.get_text().strip() if text_element else link.get_text().strip()
                
                low_href = href.lower()
                low_text = text.lower()
                
                # De Sniper-Logica per krant
                is_match = False
                if name == "NRC" and (today_path in href or yesterday_path in href):
                    is_match = True
                elif name == "Volkskrant" and ("televisie" in low_href or "recensie" in low_text):
                    is_match = True
                elif name == "Trouw" and ("bos" in low_href or "blik" in low_text):
                    is_match = True
                elif name == "Parool" and ("lips" in low_href or "han" in low_text):
                    is_match = True
                elif name == "Telegraaf" and ("marcel" in low_href or "media" in low_href):
                    is_match = True

                if is_match and len(text) > 10:
                    full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href}"
                    # Voorkom dubbelingen
                    if any(full_url in r for r in results): continue
                    
                    archive_link = f"https://archive.is/{full_url}"
                    results.append(f"<li><strong>[{name}]</strong>: {text}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
                    found_in_source += 1
                
                if found_in_source >= 3: break
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen recensies gevonden in de geselecteerde rubrieken voor de afgelopen 48 uur.</li>"

    html_body = f"""
    <html>
        <body style='font-family: Arial, sans-serif;'>
            <h2 style='color: #333;'>📺 TV Recensies Update</h2>
            <ul style='list-style: none; padding: 0;'>
                {content}
            </ul>
        </body>
    </html>
    """
    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"Media Update: {datetime.now().strftime('%d-%m-%Y')}",
            "html": html_body,
        })
        print("✅ Mail verzonden!")
    except Exception as e:
        print(f"❌ Resend Fout: {e}")

if __name__ == "__main__":
    review_html = get_reviews()
    send_mail(review_html)
