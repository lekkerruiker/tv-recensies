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
    # De filters die we gebruiken
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-']
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # Gebruik de standaard 'html.parser' in plaats van 'xml' om crashes te voorkomen
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # In RSS-feeds zitten artikelen in <item> tags
            items = soup.find_all('item')
            
            for item in items:
                # Omdat we html.parser gebruiken op XML, zoeken we simpelweg naar de tags
                title_tag = item.find('title')
                link_tag = item.find('link')
                guid_tag = item.find('guid')

                title = title_tag.get_text(strip=True) if title_tag else ""
                # De link staat soms in <link>, soms in de tekst van <link>, of in <guid>
                link = ""
                if link_tag:
                    link = link_tag.get_text(strip=True)
                if not link and guid_tag:
                    link = guid_tag.get_text(strip=True)

                if not title or not link:
                    continue

                # De Check
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
        content = "<li>Geen media-artikelen gevonden in de RSS-feeds.</li>"

    html_body = f"""
    <html>
        <body style='font-family: sans-serif; line-height: 1.6; color: #333;'>
            <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px;'>
                <h2 style='color: #2c3e50;'>📺 TV & Media Update</h2>
                <ul style='list-style: none; padding: 0;'>
                    {content}
                </ul>
            </div>
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
