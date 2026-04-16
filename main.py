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

# We zoeken naar patronen in de URL's
KEYWORDS = {
    "NRC": ["/2026/04/", "zap"],
    "Volkskrant": ["televisie", "tv-recensie"],
    "Trouw": ["blik-van-bos", "cultuur-media"],
    "Parool": ["han-lips", "kijkt-tv"],
    "Telegraaf": ["marcel-peereboom", "entertainment/media"]
}

SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/televisie",
    "Trouw": "https://www.trouw.nl/cultuur-media",
    "Parool": "https://www.parool.nl/columns-opinie",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media"
}

def get_reviews():
    results = []
    # Vermomming als echte Chrome browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    for name, url in SOURCES.items():
        try:
            print(f"Scannen van {name}...")
            response = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Pak alle linkjes
            links = soup.find_all('a', href=True)
            found_in_source = 0
            
            for link in links:
                href = link['href'].lower()
                # Haal tekst op uit de link of onderliggende elementen
                text = link.get_text(separator=" ", strip=True)
                
                # Check of een van de keywords in de URL staat
                if any(key in href for key in KEYWORDS[name]):
                    # URL compleet maken
                    full_url = href if href.startswith('http') else f"https://www.{name.lower()}.nl{href}"
                    if "telegraaf" in name.lower() and not full_url.startswith('http'):
                        full_url = "https://www.telegraaf.nl" + href

                    # Filter: geen extreem korte teksten of dubbele links
                    if len(text) < 15 or any(full_url in r for r in results):
                        continue
                    
                    archive_link = f"https://archive.is/{full_url}"
                    results.append(f"<li><strong>[{name}]</strong>: {text}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
                    found_in_source += 1
                
                if found_in_source >= 3: break
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen recensies gevonden. De scraper kon de artikelen niet identificeren op de pagina's.</li>"

    html_body = f"""
    <html>
        <body style='font-family: sans-serif; line-height: 1.5;'>
            <h2>📺 TV Recensies Update</h2>
            <ul>{content}</ul>
        </body>
    </html>
    """
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m-%Y')}",
        "html": html_body,
    })

if __name__ == "__main__":
    review_html = get_reviews()
    send_mail(review_html)
