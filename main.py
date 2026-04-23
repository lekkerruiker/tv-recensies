import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# De 4 kranten die stabiel zijn via RSS
RSS_FEEDS = {
    "Parool": "https://www.parool.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "NRC": "https://www.nrc.nl/rss/",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def get_volkskrant_homepage_scan():
    """Scant de Volkskrant op tv-gerelateerde links (omzeilt kapotte RSS)."""
    articles = []
    try:
        # We pakken de algemene sectie-pagina, die is vaak minder streng beveiligd
        r = requests.get("https://www.volkskrant.nl/televisie", headers=HEADERS, timeout=15)
        # Zoek naar alle links die de structuur van een artikel hebben (~b...)
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?>(.*?)<', r.text, re.DOTALL)
        
        for link, title in matches:
            t_clean = re.sub('<[^<]+?>', '', title).strip()
            if len(t_clean) < 15: continue
            
            # Alleen toevoegen als het over media gaat (voorkomt ruis)
            if any(x in t_clean.lower() or x in link.lower() for x in ['tv', 'recensie', 'lips', 'weimans', 'kijkt', 'serie', 'docu']):
                full_link = f"https://www.volkskrant.nl{link}"
                if not any(a['link'] == full_link for a in articles):
                    articles.append({'title': t_clean, 'link': full_link, 'source': 'Volkskrant'})
    except: pass
    return articles[:5] # Pak de 5 meest relevante

def get_prio_level(title, link):
    t, l = title.lower(), link.lower()
    
    # 1. HARDE BLOCKS (Alleen het hoognodige wegfilteren)
    if any(x in t for x in ['boekrecensie', 'concertrecensie', 'album', 'podcast-tip']):
        return 0

    # 2. PRIO 1 (De Recensies - ruimere match voor Parool)
    # We voegen 'media' en 'cultuur-media' toe voor Parool herstel
    p1_indicators = ['han-lips', 'maaike-bos', 'peereboom', 'zap', 'televisie', 'tv-recensie', 'bekeken:']
    if any(x in l or x in t for x in p1_indicators):
        return 1

    # 3. PRIO 2 (Media Nieuws)
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        return 2
        
    return 0

def main():
    all_prio1, all_prio2, seen = [], [], set()

    # A. De Volkskrant 'Noodroute'
    for art in get_volkskrant_homepage_scan():
        all_prio1.append(art)
        seen.add(art['link'])

    # B. De 4 Kranten via RSS (hersteld naar 48 uur)
    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(requests.get(url, headers=HEADERS, timeout=10).text)
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                
                # Check datum (48 uur is veilig voor Parool)
                pub = entry.get('published_parsed')
                if pub and datetime(*pub[:6]) < (datetime.now() - timedelta(hours=48)):
                    continue

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
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})

if __name__ == "__main__":
    main()
