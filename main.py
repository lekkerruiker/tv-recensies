import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

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

# Uitgebreide headers om blokkades door de Volkskrant te voorkomen
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'nl,en-US;q=0.7,en;q=0.3',
}

def get_volkskrant_content():
    """Haalt artikelen direct van de Volkskrant TV-pagina."""
    articles = []
    # We proberen de TV-sectie direct
    url = "https://www.volkskrant.nl/televisie"
    try:
        print("Poging Volkskrant scan...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        
        # We zoeken naar de typische Volkskrant link-structuur
        # Zoals: /televisie/lange-tijd-had-jorgen-raymann-last-van-divagedrag~bbba1a5d/
        # En we pakken de titel die er vlak achter staat
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?>(.*?)<', r.text, re.DOTALL)
        
        for link, title in matches:
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            if len(clean_title) < 10: continue # Skip te korte teksten (knoppen, etc)
            
            # Alleen toevoegen als het niet al in de lijst staat
            full_link = f"https://www.volkskrant.nl{link}"
            if not any(a['link'] == full_link for a in articles):
                articles.append({
                    'title': clean_title,
                    'link': full_link,
                    'source': 'Volkskrant'
                })
        print(f"Volkskrant scan klaar. {len(articles)} kandidaten gevonden.")
    except Exception as e:
        print(f"Volkskrant fout: {e}")
    return articles

def get_prio_level(title, link):
    t, l = title.lower(), link.lower()
    # Prio 1: Recensies en bekende koppen
    if any(x in l or x in t for x in ['/televisie', '/zap', 'han-lips', 'maaike-bos', 'peereboom', 'recensie']):
        # Filter de onzin uit Prio 1
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'beurs', 'sport']):
            return 1
    # Prio 2: Media nieuws
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'polder']):
            return 2
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen = set()

    # 1. De Volkskrant 'Deep Scan'
    vk_raw = get_volkskrant_content()
    for art in vk_raw:
        prio = get_prio_level(art['title'], art['link'])
        if prio > 0:
            if prio == 1: all_prio1.append(art)
            else: all_prio2.append(art)
            seen.add(art['link'])

    # 2. De rest via de vertrouwde RSS-methode
    for name, url in FEEDS.items():
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
        body += "<h2 style='color:#e67e22; border-bottom:1px dotted #e67e22;'>⭐ Dagelijkse Recensies</h2>"
        for art in all_prio1:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    
    if all_prio2:
        body += "<h2 style='color:#2980b9; border-bottom:1px dotted #2980b9;'>📺 Media Nieuws</h2>"
        for art in all_prio2:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif; max-width:600px;'>{body}</body></html>"
            })

if __name__ == "__main__":
    main()
