import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# WEER TERUG NAAR DE BRON: Google News was een fout uitstapje.
FEEDS = {
    "Volkskrant": "https://www.volkskrant.nl/televisie/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

# Gebruik een zeer specifieke header om niet als bot herkend te worden
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

def is_very_recent(entry):
    """STRENG: Alleen artikelen van de laatste 24 uur."""
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: return False
    
    dt_entry = datetime(*pub[:6])
    # Vergelijk met NU, maximaal 24 uur verschil
    return dt_entry >= (datetime.now() - timedelta(hours=24))

def get_prio_level(title, link, source):
    t, l = title.lower(), link.lower()
    
    # 1. HARDE BLOCKS (Tegen de gidsen en oude ruis)
    blocks = ['boekrecensie', 'concertrecensie', 'uitzendschema', 'tv-gids', 'radio', 'podcast', '2003', '2004']
    if any(x in t or x in l for x in blocks):
        return 0

    # 2. PRIO 1 (Recensies)
    # Focus op bekende namen en het pad 'televisie'
    if any(x in l for x in ['/televisie', 'han-lips', 'maaike-bos', 'peereboom', 'zap']):
        # Zorg dat we geen algemene 'cultuur' of 'columns' pakken die niet over TV gaan
        if any(x in t or x in l for x in ['tv', 'recensie', 'kijkt', 'serie', 'docu']):
            return 1

    # 3. PRIO 2 (Media Nieuws)
    # Alleen als 'tv' of 'omroep' een heel woord is (\b)
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'asiel']):
            return 2
            
    return 0

def main():
    all_prio1, all_prio2, seen = [], [], set()

    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}...")
            # We gebruiken een timeout en sessie om stabieler te zijn
            session = requests.Session()
            resp = session.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.text)
            
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                
                # STRENGSTE DATUM CHECK
                if not is_very_recent(entry):
                    continue
                
                title = entry.get('title', '').strip()
                prio = get_prio_level(title, link, name)
                
                if prio > 0:
                    item = {'title': title, 'link': link, 'source': name}
                    if prio == 1: all_prio1.append(item)
                    else: all_prio2.append(item)
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
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print("Mail verzonden!")
    else:
        print("Geen verse artikelen gevonden (jonger dan 24 uur).")

if __name__ == "__main__":
    main()
