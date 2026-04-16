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
            # We gebruiken BeautifulSoup om de ruwe XML-tekst te doorzoeken
            soup = BeautifulSoup(resp.content, 'html.parser')
            items = soup.find_all('item')
            
            for item in items:
                # We pakken de inhoud van de tags handmatig om parser-fouten te omzeilen
                title = ""
                if item.title:
                    title = item.title.get_text(strip=True)
                
                # De link is lastig in HTML-parsers, we proberen verschillende methodes
                link = ""
                if item.link:
                    link = item.link.next_sibling.strip() if item.link.next_sibling else item.link.get_text(strip=True)
                
                # Als dat niet werkt (vaak bij NRC/VK), pakken we de GUID of de ruwe tekst
                if not link or len(link) < 10:
                    guid = item.find('guid')
                    if guid:
                        link = guid.get_text(strip=True)

                if not title or not link or not link.startswith('http'):
                    continue

                combined_text = (title + " " + link).lower()
                if any(k in combined_text for k in KEYWORDS):
                    # Unieke check
                    if not any(link in r for r in results):
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen nieuwe recensies gevonden.</li>"

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
