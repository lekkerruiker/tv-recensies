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
    "Volkskrant": "https://www.volkskrant.nl/kijk-en-luister/rss.xml",
    "Trouw": "https://www.trouw.nl/cultuur-media/rss.xml",
    "Parool": "https://www.parool.nl/columns-opinie/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media/rss"
}

def get_reviews():
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, 'xml')
            items = soup.find_all('item')
            
            for item in items:
                title = item.find('title').get_text(strip=True) if item.find('title') else ""
                link = item.find('link').get_text(strip=True) if item.find('link') else ""
                if not link and item.find('guid'):
                    link = item.find('guid').get_text(strip=True)

                if not title or not link: continue

                low_title = title.lower()
                low_link = link.lower()
                
                # BREDE FILTERS: We pakken alles wat met media/recensie te maken heeft
                keywords = [
                    'lips', 'zap', 'bos', 'peereboom', 'marcel', 
                    'recensie', 'tv', 'serie', 'kijkt', 'kijk', 
                    'stream', 'netflix', 'videoland', 'buis'
                ]
                
                if any(k in low_title or k in low_link for k in keywords):
                    archive_link = f"https://archive.is/{link}"
                    results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    # Als er echt niets is, sturen we een lijstje met ALLES wat in de feeds staat
    # zodat je kunt zien dat de techniek werkt.
    if not content:
        content = "<li>Geen specifieke media-recensies gevonden. Misschien morgen weer!</li>"

    html_body = f"<html><body style='font-family: sans-serif;'><h2>📺 Media Update</h2><ul>{content}</ul></body></html>"
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": html_body,
    })

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
