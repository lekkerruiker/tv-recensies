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

# We herstellen de standaard RSS-feeds en voegen de Google News variant toe voor VK
FEEDS = {
    "Volkskrant": "https://news.google.com/rss/search?q=site:volkskrant.nl+televisie&hl=nl&gl=NL&ceid=NL:nl",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def is_recent(entry):
    """Check of artikel van de laatste 48 uur is."""
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: return True # Bij twijfel meenemen
    return datetime(*pub[:6]) >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link, source):
    t, l = title.lower(), link.lower()
    
    # 1. HARDE BLOCKS (Hersteld: minder streng om Parool niet te blokkeren)
    # We blokkeren alleen als het woord 'recensie' specifiek gecombineerd wordt met 'boek' of 'concert'
    if any(x in t for x in ['boekrecensie', 'concertrecensie', 'albumrecensie']):
        return 0

    # 2. PRIO 1 (Recensies & Media-secties)
    # Voor Parool en VK kijken we naar de URL-structuur
    prio1_keywords = ['han-lips', 'maaike-bos', 'peereboom', 'zap', 'televisie', 'tv-recensie', 'bekeken:']
    if any(x in l or x in t for x in prio1_keywords):
        # Dubbele check: geen politiek of klimaat in de titel
        if not any(x in t for x in ['klimaat', 'stikstof', 'oekraïne']):
            return 1

    # 3. PRIO 2 (Algemeen Media Nieuws)
    # Gebruik \b voor hele woorden tegen 'inpoldering'
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming|omroep|kijkcijfers)\b', t):
        return 2
            
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen = set()

    print("Starten van de herstelde Media Scraper...")

    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}...")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.text)
            
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                
                # Datum check (behalve voor Google News/VK, die is soms lastig te parsen)
                if name != "Volkskrant" and not is_recent(entry):
                    continue
                
                title = entry.get('title', '').strip()
                # Bij Google News de bron-naam uit de titel halen (bijv. "Titel - Volkskrant")
                if " - Volkskrant" in title:
                    title = title.split(" - Volkskrant")[0]

                prio = get_prio_level(title, link, name)
                
                if prio > 0:
                    item = {'title': title, 'link': link, 'source': name}
                    if prio == 1:
                        all_prio1.append(item)
                    else:
                        all_prio2.append(item)
                    seen.add(link)
        except Exception as e:
            print(f"Fout bij {name}: {e}")

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
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print("E-mail verzonden!")

if __name__ == "__main__":
    main()
