import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime

# 1. Instellingen en Secrets ophalen
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# Veiligheidscheck: Stoppen als de basisinstellingen ontbreken
if not API_KEY or not EMAIL_RECEIVER:
    print("❌ FOUT: Geen API_KEY of EMAIL_RECEIVER gevonden in GitHub Secrets.")
    print(f"DEBUG: Key aanwezig: {'Ja' if API_KEY else 'Nee'}")
    print(f"DEBUG: Ontvanger aanwezig: {'Ja' if EMAIL_RECEIVER else 'Nee'}")
    sys.exit(1)

resend.api_key = API_KEY

# 2. De Scraper
SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/kijk-en-luister",
    "Parool": "https://www.parool.nl/media"
}

def get_reviews():
    print("🔍 Scraper gestart...")
    results = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for name, url in SOURCES.items():
        try:
            print(f"Checking {name}...")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            found_count = 0
            for link in links:
                href = link['href']
                text = link.get_text().strip()
                
                # Filter op recensies (eenvoudige vibe-check op tekst)
                if len(text) > 10 and any(keyword in text.lower() for keyword in ['recensie', 'tv', 'kijk']):
                    if not href.startswith('http'):
                        # Maak van relatieve link een volledige link
                        base = "https://www.nrc.nl" if "nrc" in name.lower() else "https://www.volkskrant.nl" if "volks" in name.lower() else "https://www.parool.nl"
                        href = base + href if href.startswith('/') else base + '/' + href
                    
                    # Directe archive.is link genereren
                    archive_link = f"https://archive.is/{href}"
                    
                    results.append(f"<li><strong>{name}</strong>: {text}<br><a href='{archive_link}'>Lees via Archive.is</a></li><br>")
                    found_count += 1
                
                if found_count >= 3: # Max 3 per krant
                    break
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

# 3. De Mailer
def send_mail(content):
    if not content:
        print("Empty Content: Geen recensies gevonden vandaag.")
        content = "<li>Geen nieuwe recensies gevonden met de huidige zoektermen.</li>"

    print("✉️ Mail verzenden via Resend...")
    
    html_body = f"""
    <html>
        <body style='font-family: sans-serif; line-height: 1.6;'>
            <h1 style='color: #333;'>Dagelijkse TV-Updates</h1>
            <p>Hier zijn de recensies van vandaag:</p>
            <ul>
                {content}
            </ul>
            <hr>
            <p style='font-size: 0.8em; color: #666;'>Gemaakt met vibe-coding & Resend.</p>
        </body>
    </html>
    """

    try:
        params = {
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"TV Recensies - {datetime.now().strftime('%d-%m-%Y')}",
            "html": html_body,
        }
        
        email = resend.Emails.send(params)
        print(f"✅ Succes! Mail verzonden. ID: {email['id']}")
    except Exception as e:
        print(f"❌ Resend Fout: {e}")
        sys.exit(1)

# 4. Main Execution
if __name__ == "__main__":
    review_html = get_reviews()
    send_mail(review_html)
