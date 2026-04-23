import os
import requests
import feedparser
from datetime import datetime, timedelta
import re
import time

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def get_volkskrant_items():
    """Haalt artikelen op van de Volkskrant via de meest betrouwbare weg."""
    items = []
    # We proberen de sectie-pagina direct te scrapen
    url = "https://www.volkskrant.nl/televisie"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        # We zoeken naar de artikel-links (~b...) en de titels die in de buurt staan
        # Deze regex is robuuster voor de huidige Volkskrant structuur
        matches = re.findall(r'href="(/televisie/[^"]+?~b[^"]+?)".*?><h[^>]*>(.*?)</h', r.text, re.DOTALL)
        
        for link, title in matches[:10]:
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            full_link = f"https://www.volkskrant.nl{link}"
            # Omdat we van de webpagina scrapen hebben we geen datum, 
            # dus we vertrouwen erop dat de bovenste artikelen 'nieuw' zijn.
            items.append({
                'title': clean_title,
                'link': full_link,
                'source': 'Volkskrant',
                'prio': 1
            })
    except Exception as e:
        print(f"Volkskrant scrape fout: {e}")
    return items

def is_recent(entry):
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: return False
    return datetime(*pub[:6]) >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link, source):
    t, l = title.lower(), link.lower()
    
    # Blokkeer ongewenste recensies (boek/concert)
    if any(x in t for x in ['boekrecensie', 'concertrecensie', 'theater', 'literatuur', 'popmuziek', 'album']) and 'tv' not in t:
        return 0

    # Prio 1
    if any(x in l for x in ['han-lips', 'maaike-bos', 'peereboom', 'zap', '/televisie/']):
        return 1
    if any(x in t for x in ['tv-recensie', 'zap:', 'bekeken:']):
        return 1

    # Prio 2
    if re.search(r'\b(tv|televisie|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'asiel', 'polder']):
            return 2
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen = set()

    # 1. Volkskrant Special (Direct van de site)
    vk_items = get_volkskrant_items()
    for art in vk_items:
        if art['link'] not in seen:
            all_prio1.append(art)
            seen.add(art['link'])

    # 2. De rest via RSS
    for name, url in FEEDS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen or not is_recent(entry): continue
                prio = get_prio_level(entry.get('title', ''), link, name)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1: all_prio1.append(item)
                    else: all_prio2.append(item)
                    seen.add(link)
        except: continue

    # E-mail verzenden (ongewijzigd)
    body = ""
    if all_prio1:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Recensies</h2>"
        for art in all_prio1:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    if all_prio2:
        body += "<h2 style='color:#2980b9; border-bottom:1px solid #2980b9;'>📺 Media Nieuws</h2>"
        for art in all_prio2:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})

if __name__ == "__main__":
    main()
