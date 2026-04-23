import os
import requests
import feedparser
from datetime import datetime, timedelta
import re
import urllib.parse

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_google_news_articles(source, query):
    """Haalt actuele DPG artikelen op via Google News Proxy."""
    articles = []
    search_query = f'site:{source.lower()}.nl {query}'
    encoded_query = urllib.parse.quote(search_query)
    # We voegen 'when:2d' toe aan de query om alleen artikelen van de laatste 2 dagen te pakken
    url = f"https://news.google.com/rss/search?q={encoded_query}+when:2d&hl=nl&gl=NL&ceid=NL:nl"
    
    try:
        resp = requests.get(url, timeout=15)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:8]:
            title = entry.title.split(' - ')[0]
            # Strikte check om oude troep of ruis te voorkomen
            if any(x in title.lower() for x in ['tv', 'recensie', 'lips', 'bos', 'kijkt', 'serie', 'docu']):
                if not any(x in title.lower() for x in ['boek', 'concert', 'podcast-tip']):
                    articles.append({'title': title, 'link': entry.link, 'source': source})
    except: pass
    return articles

def get_prio_level(title, link):
    """De herstelde logica voor NRC, Telegraaf en Trouw."""
    t, l = title.lower(), link.lower()
    
    # 1. Blocks (Scunthorpe)
    if any(x in t for x in ['boekrecensie', 'concertrecensie', 'kerkdienst', 'stikstof', 'album']):
        return 0
    
    # 2. Prio 1: Recensies en bekende namen
    p1_names = ['han-lips', 'maaike-bos', 'peereboom', 'zap', 'televisie', 'tv-recensie']
    if any(x in l or x in t for x in p1_names):
        return 1
        
    # 3. Prio 2: Media Nieuws (Strict op hele woorden)
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        return 2
        
    return 0

def main():
    all_articles = []
    seen_links = set()

    # 1. DPG Kranten via de werkende Google Proxy (Gelimiteerd op tijd)
    all_articles.extend(get_google_news_articles("Volkskrant", "televisie"))
    all_articles.extend(get_google_news_articles("Parool", "televisie Han Lips"))

    # 2. Andere Kranten via de stabiele RSS
    RSS_FEEDS = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(requests.get(url, timeout=10).text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                
                # Datum check voor RSS (max 48 uur)
                pub = entry.get('published_parsed')
                if pub and datetime(*pub[:6]) < (datetime.now() - timedelta(hours=48)):
                    continue
                
                prio = get_prio_level(title, link)
                if prio > 0 and link not in seen_links:
                    all_articles.append({'title': title, 'link': link, 'source': name})
                    seen_links.add(link)
        except: continue

    # E-mail verzenden
    body = ""
    if all_articles:
        # Sorteer zodat Volkskrant en Parool bovenaan staan (meestal Prio 1)
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in all_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})

if __name__ == "__main__":
    main()
