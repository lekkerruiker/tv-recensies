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

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_reviews():
    results = []
    feed_samples = ""
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-']
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, 'xml')
            items = soup.find_all('item')
            
            # Pak de eerste titel voor de debug mail
            if items:
                feed_samples += f"<li>{name} eerste item: {items[0].title.get_text()[:50]}...</li>"

            for item in items:
                title = item.find('title').get_text(strip=True) if item.find('title') else ""
                link = item.find('link').get_text(strip=True) if item.find('link') else ""
                if not link and item.find('guid'):
                    link = item.find('guid').get_text(strip=True)

                if not title or not link: continue

                # Check op keywords
                txt = (title + " " + link).lower()
                if any(k in txt for k in KEYWORDS):
                    if not any(link in r for r in results):
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        
        except Exception as e:
            feed_samples += f"<li>{name} Fout: {str(e)[:30]}</li>"
            
    if not results:
        return f"<li>Niets gevonden met filters.</li><p><strong>Wat de scraper wel zag:</strong></p><ul>{feed_samples}</ul>"
    return "".join(results)

def send_mail(content):
    html_body = f"<html><body><h2>📺 Media Update</h2><ul>{content}</ul></body></html>"
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": html_body,
    })

if __name__ == "__main__":
    send_mail(get_reviews())
