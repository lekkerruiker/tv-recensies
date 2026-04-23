import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# Deze kranten gaan goed via RSS
RSS_FEEDS = {
    "Parool": "https://www.parool.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "NRC": "https://www.nrc.nl/rss/",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def get_volkskrant_from_archive():
    """Grijpt artikelen direct uit het Volkskrant archief van gisteren."""
    articles = []
    # Formatteer de datum van gisteren: bijv. 2026/04/22
    gisteren = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    url = f"https://www.volkskrant.nl/archief/{gisteren}"
    
    try:
        print(f"Scannen van Volkskrant archief: {url}")
        r = requests.get(url, headers=HEADERS, timeout=15)
        # We zoeken links met de ID structuur (~b...) en de tekst in de kopjes
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?><h[^>]*>(.*?)</h', r.text, re.DOTALL)
        
        for link, title in matches:
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            # Filter op media-relevante termen
            if any(x in clean_title.lower() or x in link.lower() for x in ['tv', 'recensie', 'lips', 'weimans', 'kijkt', 'serie', 'docu']):
                full_link = f"https://www.volkskrant.nl{link}"
                if not any(a['link'] == full_link for a in articles):
                    articles.append({'title': clean_title, 'link': full_link, 'source': 'Volkskrant'})
    except Exception as e:
        print(f"Archief fout: {e}")
    return articles

def get_prio_level_strict(title, link):
    """De bewezen filter tegen ruis."""
    t, l = title.lower(), link.lower()
    
    # 1. VIP namen & Harde Recensie termen (Prio 1)
    if any(x in l for x in ['han-lips', 'maaike-bos', 'peereboom', 'zap']): return 1
    if any(x in t for x in ['tv-recensie', 'zap:', 'bekeken:']): return 1

    # 2. Media Check (Prio 2)
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming)\b', t):
        # Filter Scunthorpe-problemen (kerkdienst, stikstof, etc.)
        if not any(x in t for x in ['stikstof', 'oekraïne', 'kerkdienst', 'sport', 'voetbal', 'beurs']):
            return 2
            
    return 0

def main():
    all_articles = []
    seen = set()

    # 1. Volkskrant via de Archief-route
    vk_results = get_volkskrant_from_archive()
    for art in vk_results:
        all_articles.append(art)
        seen.add(art['link'])

    # 2. De rest (inclusief Parool) via RSS
    for name, url in RSS_FEEDS.items():
        try:
            print(f"Scannen RSS: {name}")
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                if not link or link in seen: continue
                
                # Check of het artikel recent is (48 uur voor RSS)
                pub = entry.get('published_parsed')
                if pub and datetime(*pub[:6]) < (datetime.now() - timedelta(hours=48)):
                    continue

                prio = get_prio_level_strict(title, link)
                if prio > 0:
                    all_articles.append({'title': title, 'link': link, 'source': name})
                    seen.add(link)
        except: continue

    # E-mail opbouw
    body = ""
    if all_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        # Sorteer op bron voor overzicht
        for art in sorted(all_articles, key=lambda x: x['source']):
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})

if __name__ == "__main__":
    main()
