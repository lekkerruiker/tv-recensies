import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_specific_media_articles():
    """Haalt alleen artikelen op die 100% zeker over media gaan."""
    articles = []
    seen_links = set()
    
    # We gebruiken Google News alleen voor de 2 lastigste bronnen, 
    # maar met een veel striktere zoekopdracht.
    queries = [
        ("Parool", "Han+Lips"),
        ("Volkskrant", "televisie+recensie")
    ]
    
    limit = datetime.now() - timedelta(hours=48)
    
    for source, q in queries:
        rss_url = f"https://news.google.com/rss/search?q=site:{source.lower()}.nl+{q}+when:2d&hl=nl&gl=NL&ceid=NL:nl"
        try:
            feed = feedparser.parse(requests.get(rss_url, timeout=15).text)
            for entry in feed.entries:
                pub_date = datetime(*entry.published_parsed[:6])
                if pub_date < limit: continue
                
                title = entry.title.split(' - ')[0]
                link = entry.link
                
                # DE HARDSTE FILTER CHECK
                # Moet media-gerelateerd zijn EN mag geen algemene ruis bevatten
                t_l = (title + link).lower()
                is_media = any(x in t_l for x in ['han-lips', 'televisie', 'recensie', 'maaike-bos', 'kijkcijfers', 'talkshow'])
                is_noise = any(x in t_l for x in ['koningsdag', 'marathon', 'voetbal', 'ajax', 'feyenoord', 'overleden', 'brand', 'steekpartij', 'politie', 'fatbike'])
                
                if is_media and not is_noise and link not in seen_links:
                    articles.append({'title': title, 'link': link, 'source': source})
                    seen_links.add(link)
        except: pass

    # Overige bronnen via RSS (NRC, Telegraaf, Trouw)
    rss_feeds = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }
    
    for source, url in rss_feeds.items():
        try:
            feed = feedparser.parse(requests.get(url, timeout=15).text)
            for entry in feed.entries:
                title = entry.title
                link = entry.link
                t_l = (title + link).lower()
                
                # Alleen Prio 1 termen
                if any(x in t_l for x in ['tv-recensie', 'maaike-bos', 'zap:', 'bekeken:']) and link not in seen_links:
                    articles.append({'title': title, 'link': link, 'source': source})
                    seen_links.add(link)
        except: pass

    return articles

def main():
    all_articles = get_specific_media_articles()

    if all_articles:
        body = "<h2>⭐ Media Focus: De Selectie</h2>"
        # Sorteren op bron
        for art in sorted(all_articles, key=lambda x: x['source']):
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
        print("Geen relevante media-artikelen gevonden.")

if __name__ == "__main__":
    main()
