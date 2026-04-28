import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'nl-NL,nl;q=0.9'
}

def get_volkskrant_archive_exact():
    """Scant de archiefpagina van gisteren en pakt ELK artikel uit de televisiesectie."""
    articles = []
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    url = f"https://www.volkskrant.nl/archief/{yesterday}"
    
    try:
        print(f"Scannen Volkskrant archief: {url}")
        r = requests.get(url, headers=HEADERS, timeout=20)
        # We zoeken specifiek naar links die /televisie/ in het pad hebben
        # De regex pakt de link en de titel die er direct achter staat
        matches = re.findall(r'href="(/televisie/[^"]+?~b[^"]+?)".*?><h[^>]*>(.*?)</h', r.text, re.DOTALL)
        
        for link, title in matches:
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            articles.append({
                'title': clean_title,
                'link': f"https://www.volkskrant.nl{link}",
                'source': 'Volkskrant'
            })
            print(f"  Gevonden in archief: {clean_title}")
    except Exception as e:
        print(f"Archief scan fout: {e}")
    return articles

def main():
    all_articles = []
    seen_links = set()

    # 1. Volkskrant: Harde scan op het archief van gisteren (geen zoekwoorden nodig!)
    vk_articles = get_volkskrant_archive_exact()
    all_articles.extend(vk_articles)
    for a in vk_articles: seen_links.add(a['link'])

    # 2. De overige kranten via de vertrouwde RSS
    RSS_FEEDS = {
        "Parool": "https://www.parool.nl/rss.xml",
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(requests.get(url, headers=HEADERS, timeout=15).text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                if not link or link in seen_links: continue
                
                # Datum check (48 uur)
                pub = entry.get('published_parsed')
                if pub and datetime(*pub[:6]) < (datetime.now() - timedelta(hours=48)):
                    continue
                
                # Filter voor RSS kranten (iets ruimer voor Parool/Han Lips)
                t_l = (title + link).lower()
                if any(x in t_l for x in ['televisie', 'tv-recensie', 'han-lips', 'zap:', 'bekeken:']):
                    if not any(x in title.lower() for x in ['boek', 'concert', 'stikstof']):
                        all_articles.append({'title': title, 'link': link, 'source': name})
                        seen_links.add(link)
        except: continue

    # E-mail verzenden
    body = ""
    if all_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in all_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})

if __name__ == "__main__":
    main()
