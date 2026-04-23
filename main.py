import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# We houden de andere kranten op RSS, maar voegen een handmatige check toe voor VK
FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_volkskrant_tv_articles():
    """Scrape direct de HTML van de Volkskrant TV sectie omdat de RSS onbetrouwbaar is."""
    articles = []
    url = "https://www.volkskrant.nl/televisie"
    try:
        print("Directe scan van Volkskrant TV-sectie...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        # Zoek naar links die lijken op artikelen in de televisie sectie
        # De regex zoekt naar patronen zoals /televisie/titel-van-artikel~b12345/
        links = re.findall(r'href="(/televisie/[^"]+?~b[^"]+?)"', r.text)
        
        for rel_link in list(set(links))[:10]: # Pak de 10 nieuwste unieke links
            full_link = f"https://www.volkskrant.nl{rel_link}"
            # Maak een leesbare titel van de slug (bij gebrek aan RSS titel)
            slug = rel_link.split('/')[-1].split('~')[0].replace('-', ' ').capitalize()
            articles.append({
                'title': slug,
                'link': full_link,
                'source': 'Volkskrant',
                'prio': 1 # Alles in deze sectie is Prio 1
            })
    except Exception as e:
        print(f"Fout bij handmatige Volkskrant scan: {e}")
    return articles

def get_prio_level(title, link):
    t, l = title.lower(), link.lower()
    if any(x in l for x in ['/zap', 'han-lips', 'maaike-bos', 'peereboom']): return 1
    if any(x in t for x in ['tv-recensie', 'han lips', 'maaike bos', 'zap:', 'bekeken:']): return 1
    
    # Strikte Media Check (Prio 2)
    if re.search(r'\b(tv|televisie|npo|rtl|sbs|videoland|netflix|streaming|omroep|ongehoord nederland)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'economie']):
            return 2
    return 0

def main():
    all_articles = {'prio1': [], 'potential': []}
    seen = set()

    # 1. Haal Volkskrant op via de nieuwe methode
    vk_articles = get_volkskrant_tv_articles()
    for art in vk_articles:
        all_articles['prio1'].append(art)
        seen.add(art['link'])

    # 2. Haal de rest op via RSS
    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}")
            feed = feedparser.parse(requests.get(url, headers=HEADERS).text)
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                prio = get_prio_level(entry.get('title', ''), link)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1: all_articles['prio1'].append(item)
                    else: all_articles['potential'].append(item)
                    seen.add(link)
        except Exception as e: print(f"Fout bij {name}: {e}")

    # E-mail bouwen
    body = ""
    for level, section, color in [('prio1', '⭐ Dagelijkse Recensies', '#e67e22'), ('potential', '📺 Media Nieuws', '#2980b9')]:
        if all_articles[level]:
            body += f"<h2 style='color:{color}; border-bottom:1px solid {color};'>{section}</h2>"
            for art in all_articles[level]:
                body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body>{body}</body></html>"
            })
        print("Mail verzonden!")

if __name__ == "__main__":
    main()
