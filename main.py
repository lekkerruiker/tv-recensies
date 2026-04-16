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
    sys.exit(1)

resend.api_key = API_KEY

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_reviews():
    results = []
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # We laden de ruwe content in BeautifulSoup
            soup = BeautifulSoup(resp.content, 'html.parser')
            items = soup.find_all('item')
            
            for item in items:
                # TITEL VINDEN: We proberen 3 methodes voor maximale kans op tekst
                title = ""
                if item.title:
                    # Methode 1: Directe tekst (voor Parool/Telegraaf)
                    title = item.title.get_text(strip=True)
                    # Methode 2: Als methode 1 leeg is, kijk naar de 'next_sibling' (voor CDATA blokken)
                    if not title and item.title.string:
                        title = item.title.string.strip()
                
                # LINK VINDEN
                link = ""
                # We zoeken eerst naar de tekst in de link tag
                if item.link:
                    link = item.link.get_text(strip=True)
                # Als dat niet werkt, proberen we de GUID
                if not link and item.find('guid'):
                    link = item.find('guid').get_text(strip=True)
                
                # De "Vibe-Check": als we nog steeds geen link hebben, is het item onbruikbaar
                if not link or not link.startswith('http'):
                    continue
                
                # Als de titel nog steeds leeg is, gebruiken we een deel van de URL als nood-titel
                if not title:
                    title = link.split('/')[-1].replace('-', ' ').replace('.html', '').capitalize()

                combined_text = (title + " " + link).lower()
                if any(k in combined_text for k in KEYWORDS):
                    if not any(link in r for r in results):
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen nieuwe recensies gevonden vandaag.</li>"

    html_body = f"""
    <html>
        <body style='font-family: Arial, sans-serif; line-height: 1.6;'>
            <h2 style='color: #2c3e50;'>📺 TV & Media Update</h2>
            <ul style='list-style: none; padding: 0;'>
                {content}
            </ul>
        </body>
    </html>
    """
    
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": html_body,
    })

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
