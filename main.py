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
    articles = []
    seen_links = set()
    limit = datetime.now() - timedelta(hours=72) # Iets ruimer voor het weekend
    
    # 1. DPG via Google News (Volkskrant & Parool)
    # We zoeken nu heel specifiek op de secties
    queries = [
        ("Parool", "Han+Lips"), 
        ("Volkskrant", "inurl:televisie")
    ]
    
    for source, q in queries:
        try:
            rss_url = f"https://news.google.com/rss/search?q=site:{source.lower()}.nl+{q}+when:3d&hl=nl&gl=NL&ceid=NL:nl"
            feed = feedparser.parse(requests.get(rss_url, timeout=15).text)
            for entry in feed.entries:
                title = entry.title.split(' - ')[0]
                link = entry.link
                t_l = (title + link).lower()
                
                # Check of het een "Hard Target" is (moet altijd doorlaten)
                is_vip = any(x in t_l for x in ['han-lips', 'televisie', 'recensie', 'maaike-bos'])
                
                # Alleen uitsluiten als het GEEN VIP artikel is
                is_noise = False
                if not is_vip:
                    is_noise = any(x in t_l for x in ['voetbal', 'ajax', 'steekpartij', 'brand', 'fatbike'])
                
                if is_vip and not is_noise and link not in seen_links:
                    articles.append({'title': title, 'link': link, 'source': source})
                    seen_links.add(link)
        except: pass

    # 2. Overige via RSS (NRC, Telegraaf, Trouw)
    rss_feeds = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }
    for source, url in rss_feeds.items():
        try:
            feed = feedparser.parse(requests.get(url, timeout=15).text)
            for entry in feed.entries:
                title = entry.get('title', '')
                link = entry.get('link', '')
                t_l = (title + link).lower()
                
                # NRC specifieke check voor die Koningsdag recensie
                # We kijken of 'televisie' in de URL staat of 'zap' in de titel
                if any(x in t_l for x in ['/televisie/', 'zap:', 'bekeken:', 'maaike-bos', 'tv-recensie']):
                    if link not in seen_links:
                        articles.append({'title': title, 'link': link, 'source': source})
                        seen_links.add(link)
        except: pass

    return articles

def main():
    try:
        all_articles = get_specific_media_articles()
        
        if all_articles:
            body = "<h2>⭐ Media Focus: De Selectie</h2>"
            # Sorteer op bron
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
            # Stuur nog steeds een mail als er niets is, zodat je weet dat het script draait
            requests.post("https://api.resend.com/emails", 
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                    "subject": "Media Focus: Geen nieuwe artikelen", 
                    "html": "<html><body>Geen nieuwe media-artikelen gevonden in de afgelopen 72 uur.</body></html>"
                })
    except Exception as e:
        print(f"Fout: {e}")

if __name__ == "__main__":
    main()
