import os
import requests
import feedparser
from datetime import datetime
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_via_google_specific(source, search_term):
    """Zoekt zeer specifiek binnen één bron via Google RSS."""
    articles = []
    # We zoeken nu op de exacte naam of sectie-URL
    rss_url = f"https://news.google.com/rss/search?q=site:{source.lower()}.nl+{search_term}&hl=nl&gl=NL&ceid=NL:nl"
    try:
        resp = requests.get(rss_url, timeout=15)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:15]:
            title = entry.title.split(' - ')[0]
            link = entry.link
            
            # STRENG FILTER: uitsluiten van film, concert, theater, boek
            if any(x in title.lower() for x in ['film', 'concert', 'theater', 'boek', 'album', 'podcast']):
                continue
                
            articles.append({'title': title, 'link': link, 'source': source})
    except: pass
    return articles

def get_rss_strict(name, url):
    """RSS voor NRC, Telegraaf, Trouw met verbeterde filters."""
    articles = []
    try:
        feed = feedparser.parse(requests.get(url, timeout=15).text)
        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            
            # Prio indicators
            if any(x in (title + link).lower() for x in ['tv-recensie', 'maaike-bos', 'zap:', 'bekeken:']):
                if not any(x in title.lower() for x in ['film', 'boek', 'concert']):
                    articles.append({'title': title, 'link': link, 'source': name})
    except: pass
    return articles

def main():
    all_articles = []
    seen = set()

    # 1. PAROOL: Specifiek zoeken op Han Lips (zo vangen we de Amsterdam Centraal recensie)
    all_articles.extend(get_via_google_specific("Parool", "Han+Lips"))
    
    # 2. VOLKSKRANT: Zoeken op de sectie televisie (voor de Oranjezondag recensie)
    all_articles.extend(get_via_google_specific("Volkskrant", "inurl:televisie"))

    # 3. OVERIG: De rest via RSS
    feeds = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }
    for name, url in feeds.items():
        all_articles.extend(get_rss_strict(name, url))

    # Uniek maken
    final_list = []
    for art in all_articles:
        if art['link'] not in seen:
            final_list.append(art)
            seen.add(art['link'])

    # Mail opbouwen
    if final_list:
        body = "<h2>⭐ Media Focus Selectie</h2>"
        # Sorteer op bron voor de leesbaarheid
        for art in sorted(final_list, key=lambda x: x['source']):
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    else:
        body = "<p>Geen nieuwe recensies gevonden met de huidige filters.</p>"

    # Versturen
    requests.post("https://api.resend.com/emails", 
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM, 
            "to": [EMAIL_RECEIVER], 
            "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", 
            "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
        })

if __name__ == "__main__":
    main()
