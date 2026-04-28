import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_via_google_specific(source, search_term):
    """Zoekt specifiek binnen één bron en filtert STRENG op datum (laatste 48u)."""
    articles = []
    # De 'when:2d' in de query helpt Google alvast te focussen
    rss_url = f"https://news.google.com/rss/search?q=site:{source.lower()}.nl+{search_term}+when:2d&hl=nl&gl=NL&ceid=NL:nl"
    
    try:
        resp = requests.get(rss_url, timeout=15)
        feed = feedparser.parse(resp.text)
        
        # We definiëren de tijdslimiet: nu min 48 uur
        limit = datetime.now() - timedelta(hours=48)
        
        for entry in feed.entries:
            # Controleer de publicatiedatum die Google meestuurt
            pub_date = datetime(*entry.published_parsed[:6])
            
            if pub_date < limit:
                continue # Te oud, overslaan
                
            title = entry.title.split(' - ')[0]
            link = entry.link
            
            # Negatieve filters voor ruis
            if any(x in title.lower() for x in ['film', 'concert', 'theater', 'boek', 'album', 'podcast']):
                continue
                
            articles.append({'title': title, 'link': link, 'source': source})
    except: pass
    return articles

def get_rss_strict(name, url):
    """RSS voor NRC, Telegraaf, Trouw met datumfilter."""
    articles = []
    try:
        feed = feedparser.parse(requests.get(url, timeout=15).text)
        limit = datetime.now() - timedelta(hours=48)
        
        for entry in feed.entries:
            pub_date = datetime(*entry.published_parsed[:6])
            if pub_date < limit:
                continue
                
            title = entry.get('title', '')
            link = entry.get('link', '')
            
            if any(x in (title + link).lower() for x in ['tv-recensie', 'maaike-bos', 'zap:', 'bekeken:', 'han-lips']):
                if not any(x in title.lower() for x in ['film', 'boek', 'concert']):
                    articles.append({'title': title, 'link': link, 'source': name})
    except: pass
    return articles

def main():
    all_articles = []
    seen = set()

    # 1. DPG: Specifiek zoeken met tijdstempel check
    all_articles.extend(get_via_google_specific("Parool", "Han+Lips"))
    all_articles.extend(get_via_google_specific("Volkskrant", "inurl:televisie"))

    # 2. OVERIG: RSS met datumcheck
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
        body = "<h2>⭐ Media Focus: Laatste 48 uur</h2>"
        for art in sorted(final_list, key=lambda x: x['source']):
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
        
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
    else:
        print("Geen nieuwe artikelen in de afgelopen 48 uur.")

if __name__ == "__main__":
    main()
