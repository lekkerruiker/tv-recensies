import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# Kranten die goed gaan via RSS
RSS_FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_volkskrant_direct():
    """De herstelde methode: direct de HTML van de TV-sectie uitlezen."""
    articles = []
    # We gebruiken de tag-pagina die je eerder voorstelde, die is het meest compleet
    url = "https://www.volkskrant.nl/tag/televisie"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        # Deze specifieke regex haalde eerder de artikelen binnen:
        # Hij zoekt naar links met een ID (~b...) en de tekst in de kopjes
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?><h[^>]*>(.*?)</h', r.text, re.DOTALL)
        
        for link, title in matches[:10]:
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            # Filter: We willen alleen media, geen politiek/klimaat
            if any(x in clean_title.lower() or x in link.lower() for x in ['tv', 'recensie', 'lips', 'weimans', 'raymann', 'kijkt', 'serie', 'docu', 'omroep']):
                articles.append({
                    'title': clean_title,
                    'link': f"https://www.volkskrant.nl{link}",
                    'source': 'Volkskrant',
                    'prio': 1
                })
    except Exception as e:
        print(f"Fout bij directe Volkskrant-check: {e}")
    return articles

def get_prio_level(title, link):
    t, l = title.lower(), link.lower()
    # VIP check voor de overige kranten
    if any(x in l for x in ['/zap', 'han-lips', 'maaike-bos', 'peereboom']): return 1
    if any(x in t for x in ['tv-recensie', 'han lips', 'maaike bos', 'zap:', 'bekeken:']): return 1
    
    # Media Nieuws check (Prio 2) met de \b grens tegen 'inpoldering'
    if re.search(r'\b(tv|televisie|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'beurs']):
            return 2
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen = set()

    # 1. Haal Volkskrant op via de directe HTML methode (HERSTELD)
    vk_articles = get_volkskrant_direct()
    for art in vk_articles:
        all_prio1.append(art)
        seen.add(art['link'])

    # 2. Haal de rest op via RSS (zoals het goed ging)
    for name, url in RSS_FEEDS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                prio = get_prio_level(entry.get('title', ''), link)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1: all_prio1.append(item)
                    else: all_prio2.append(item)
                    seen.add(link)
        except: continue

    # E-mail opbouw
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
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })

if __name__ == "__main__":
    main()
