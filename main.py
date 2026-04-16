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

# De meest stabiele RSS feeds voor deze rubrieken
FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/kijk-en-luister/rss.xml",
    "Trouw": "https://www.trouw.nl/cultuur-media/rss.xml",
    "Parool": "https://www.parool.nl/columns-opinie/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media/rss"
}

def get_reviews():
    results = []
    all_titles_debug = [] # Om te zien wat er wél binnenkomt
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # We gebruiken 'html.parser' omdat sommige RSS-feeds niet perfecte XML zijn
            soup = BeautifulSoup(resp.content, 'html.parser')
            items = soup.find_all('item')
            
            for item in items:
                title = item.title.get_text() if item.title else ""
                link = item.link.get_text() if item.link else ""
                
                low_title = title.lower()
                low_link = link.lower()
                
                # We loggen de eerste 3 titels per krant voor debuggen
                if len(all_titles_debug) < 15:
                    all_titles_debug.append(f"{name}: {title[:50]}...")

                # ZEER BREDE FILTERS (gebaseerd op jouw auteurs en rubrieken)
                is_match = False
                # We zoeken naar de namen die je gaf, of algemene media-termen
                keywords = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'tv', 'serie', 'kijkt']
                
                if any(k in low_title or k in low_link for k in keywords):
                    is_match = True

                if is_match and len(title) > 10:
                    archive_link = f"https://archive.is/{link}"
                    results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    if not results:
        debug_list = "".join([f"<li>{t}</li>" for t in all_titles_debug])
        return f"<li>Geen match gevonden.</li><p><strong>Laatste artikelen in de feeds:</strong></p><ul>{debug_list}</ul>"
    
    return "".join(results)

def send_mail(content):
    html_body = f"""
    <html>
        <body style='font-family: sans-serif;'>
            <h3>📺 TV Update</h3>
            <ul>{content}</ul>
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
