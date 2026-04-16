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

# We pakken nu de hoofdfeeds, die bevatten VEEL meer artikelen
FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_reviews():
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # De lijst met trefwoorden die we zoeken in TITEL of URL
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-']

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # Gebruik xml parser voor stabiliteit
            soup = BeautifulSoup(resp.content, 'xml')
            items = soup.find_all('item')
            
            for item in items:
                title = item.find('title').get_text(strip=True) if item.find('title') else ""
                link = item.find('link').get_text(strip=True) if item.find('link') else ""
                
                # Als link leeg is (NRC/Telegraaf kwaaltje), check guid
                if not link and item.find('guid'):
                    link = item.find('guid').get_text(strip=True)

                if not title or not link: continue

                low_title = title.lower()
                low_link = link.lower()
                
                # Check of het een match is
                if any(k in low_title or k in low_link for k in KEYWORDS):
                    # Check voor dubbelingen
                    if any(link in r for r in results): continue
                    
                    archive_link = f"https://archive.is/{link}"
                    results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen media-artikelen gevonden in de hoofd-feeds op dit moment.</li>"

    html_body = f"""
    <html>
        <body style='font-family: sans-serif; line-height: 1.6; color: #333;'>
            <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px;'>
                <h2 style='color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;'>📺 TV & Media Update</h2>
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
