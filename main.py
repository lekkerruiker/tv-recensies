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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def get_articles_from_sitemap(source_name, sitemap_url):
    """Scant de officiële sitemap voor de allernieuwste artikelen."""
    articles = []
    try:
        print(f"Scannen sitemap: {source_name}")
        r = requests.get(sitemap_url, headers=HEADERS, timeout=20)
        # We zoeken naar alle links in de sitemap
        links = re.findall(r'<loc>(https://www\.' + source_name.lower() + r'\.nl/[^<]+?~b[^<]+?)</loc>', r.text)
        
        for link in links[:150]: # Check de 150 nieuwste links
            # We filteren op de harde sectie 'televisie' in de URL
            if '/televisie/' in link or '/columns/han-lips/' in link:
                # We halen de titel uit de URL als noodgreep, of we maken hem mooi
                # Voorbeeld: .../titel-van-het-artikel~be64d6fd/ -> titel van het artikel
                title_part = link.split('/')[-2].replace('-', ' ').capitalize()
                # Verwijder de ID aan het einde als die in de title_part zit
                title_part = re.sub(r'~b.*', '', title_part).strip()
                
                articles.append({
                    'title': title_part,
                    'link': link,
                    'source': source_name
                })
    except Exception as e:
        print(f"Sitemap fout {source_name}: {e}")
    return articles

def main():
    all_articles = []
    seen_links = set()

    # 1. Volkskrant & Parool via de Sitemap (De meest betrouwbare bron)
    all_articles.extend(get_articles_from_sitemap("Volkskrant", "https://www.volkskrant.nl/sitemap.xml"))
    all_articles.extend(get_articles_from_sitemap("Parool", "https://www.parool.nl/sitemap.xml"))

    for a in all_articles: seen_links.add(a['link'])

    # 2. De rest via de stabiele RSS
    RSS_FEEDS = {
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
                
                # Check op relevantie
                t_l = (title + link).lower()
                if any(x in t_l for x in ['televisie', 'tv-recensie', 'maaike-bos', 'zap:', 'bekeken:']):
                    if not any(x in title.lower() for x in ['boek', 'concert', 'stikstof']):
                        all_articles.append({'title': title, 'link': link, 'source': name})
                        seen_links.add(link)
        except: continue

    # E-mail opbouw
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
