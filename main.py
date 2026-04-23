import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# RSS voor de stabiele kranten
RSS_FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7'
}

def get_volkskrant_tag_articles():
    """Haalt artikelen direct van de Volkskrant Tag-pagina (de meest actuele bron)."""
    articles = []
    url = "https://www.volkskrant.nl/tag/televisie"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        # We zoeken naar de specifieke HTML-structuur van de Volkskrant tag-pagina
        # Dit zoekt naar links die eindigen op ~b... (artikel ID) en de tekst in de kopjes
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?><h[^>]*>(.*?)</h', r.text, re.DOTALL)
        
        for link, title in matches[:8]: # Pak de 8 nieuwste
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            # Filter op relevante media-termen om de tag-pagina schoon te houden
            if any(x in clean_title.lower() or x in link.lower() for x in ['tv', 'recensie', 'lips', 'weimans', 'kijkt', 'serie', 'docu', 'raymann']):
                articles.append({
                    'title': clean_title,
                    'link': f"https://www.volkskrant.nl{link}",
                    'source': 'Volkskrant',
                    'prio': 1
                })
    except Exception as e:
        print(f"Volkskrant scrape fout: {e}")
    return articles

def is_recent(entry):
    """Terug naar 48 uur om Parool en anderen niet te missen."""
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: return True 
    dt_entry = datetime(*pub[:6])
    return dt_entry >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link):
    t, l = title.lower(), link.lower()
    # Harde blocks voor gidsen en boeken
    if any(x in t for x in ['boekrecensie', 'concertrecensie', 'tv-gids', 'uitzendschema']):
        return 0
    # Prio 1: Recensies en TV-secties
    if any(x in l or x in t for x in ['han-lips', 'maaike-bos', 'peereboom', 'zap', 'televisie', 'tv-recensie']):
        return 1
    # Prio 2: Algemeen Media Nieuws
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'polder']):
            return 2
    return 0

def main():
    all_prio1, all_prio2, seen = [], [], set()

    # 1. Volkskrant (via de Tag-pagina methode)
    for art in get_volkskrant_tag_articles():
        all_prio1.append(art)
        seen.add(art['link'])

    # 2. De rest via de bewezen RSS-methode
    for name, url in RSS_FEEDS.items():
        try:
            print(f"Scannen: {name}")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.text)
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen or not is_recent(entry): continue
                prio = get_prio_level(entry.get('title', ''), link)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1: all_prio1.append(item)
                    else: all_prio2.append(item)
                    seen.add(link)
        except: continue

    # E-mail genereren
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
