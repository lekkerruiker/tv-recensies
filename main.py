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
    """Gebruikt Google News als doorgeefluik voor VK en Parool."""
    articles = []
    # We zoeken specifiek binnen de site op media termen
    search_query = f'site:{source.lower()}.nl {query}'
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=nl&gl=NL&ceid=NL:nl"
    
    try:
        resp = requests.get(url, timeout=15)
        feed = feedparser.parse(resp.text)
        
        for entry in feed.entries[:10]:
            title = entry.title
            # Google News titels eindigen vaak op " - Volkskrant"
            clean_title = title.split(' - ')[0]
            link = entry.link
            
            # Strenge filter: Alleen als media-woorden in de titel staan
            if any(x in clean_title.lower() for x in ['tv', 'recensie', 'lips', 'bos', 'kijkt', 'serie', 'docu']):
                # Filter de bekende Scunthorpe-ruis (kerk, boeken, etc)
                if not any(x in clean_title.lower() for x in ['boek', 'concert', 'kerkdienst', 'sport']):
                    articles.append({
                        'title': clean_title,
                        'link': link,
                        'source': source
                    })
    except Exception as e:
        print(f"Fout bij Google News voor {source}: {e}")
    return articles

def get_rss_strict(name, url):
    """Haalt de overige kranten op met een zeer streng filter."""
    articles = []
    try:
        feed = feedparser.parse(requests.get(url, timeout=10).text)
        for entry in feed.entries:
            title = entry.title
            link = entry.link
            
            # ZEER STRENG FILTER tegen de Trouw-ruis
            # Alleen Prio 1 namen of expliciete TV-recensie termen
            if any(x in title.lower() or x in link.lower() for x in ['han-lips', 'maaike-bos', 'tv-recensie', 'zap:', 'bekeken:']):
                articles.append({'title': title, 'link': link, 'source': name})
    except: pass
    return articles

def main():
    all_articles = []
    seen_links = set()

    # 1. Volkskrant & Parool via de Google Route
    all_articles.extend(get_google_news_articles("Volkskrant", "televisie recensie"))
    all_articles.extend(get_google_news_articles("Parool", "televisie Han Lips"))

    # 2. NRC en Telegraaf via RSS (Trouw nu ook strenger)
    all_articles.extend(get_rss_strict("NRC", "https://www.nrc.nl/rss/"))
    all_articles.extend(get_rss_strict("Telegraaf", "https://www.telegraaf.nl/rss"))
    all_articles.extend(get_rss_strict("Trouw", "https://www.trouw.nl/rss.xml"))

    # E-mail opbouw
    body = ""
    unique_articles = []
    for art in all_articles:
        if art['link'] not in seen_links:
            unique_articles.append(art)
            seen_links.add(art['link'])

    if unique_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in unique_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})
        print("Mail verstuurd met " + str(len(unique_articles)) + " artikelen.")
    else:
        print("Geen relevante artikelen gevonden.")

if __name__ == "__main__":
    main()
