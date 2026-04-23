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

# We voegen een timestamp toe om verse data te forceren
timestamp = int(time.time())
FEEDS = {
    "Volkskrant": f"https://www.volkskrant.nl/televisie/rss.xml?cb={timestamp}",
    "Trouw": f"https://www.trouw.nl/rss.xml?cb={timestamp}",
    "Parool": f"https://www.parool.nl/rss.xml?cb={timestamp}",
    "Telegraaf": f"https://www.telegraaf.nl/rss?cb={timestamp}",
    "NRC": f"https://www.nrc.nl/rss/?cb={timestamp}"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
}

def is_recent(entry):
    """Controleert streng of een artikel maximaal 48 uur oud is."""
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: 
        return False
    
    dt_entry = datetime(*pub[:6])
    nu = datetime.now()
    # Alleen artikelen van de laatste 48 uur
    return dt_entry >= (nu - timedelta(hours=48))

def get_prio_level(title, link, source):
    t, l = title.lower(), link.lower()
    
    # 1. HARDE BLOCKS (Geen boeken, concerten, etc.)
    blocks = ['boekrecensie', 'concertrecensie', 'theater', 'literatuur', 'popmuziek', 'album', 'roman', 'polder']
    if any(x in t for x in blocks) and 'tv' not in t:
        return 0

    # 2. PRIO 1 (Recensies)
    # Voor de Volkskrant is alles in de /televisie/ sectie Prio 1
    if source == "Volkskrant" and 'televisie' in l:
        return 1
    
    # VIP namen voor andere kranten
    if any(x in l for x in ['han-lips', 'maaike-bos', 'peereboom', 'zap']):
        return 1
    if any(x in t for x in ['tv-recensie', 'zap:', 'bekeken:']):
        return 1

    # 3. PRIO 2 (Media Nieuws)
    media_words = [r'\btv\b', r'\btelevisie\b', r'\bnpo\b', r'\brtl\b', r'\bsbs\b', r'\bvideoland\b', r'\bnetflix\b', r'\bstreaming\b', r'\bomroep\b']
    if any(re.search(pattern, t) or re.search(pattern, l) for pattern in media_words):
        if not any(x in t for x in ['klimaat', 'ecb', 'asiel', 'beurs']):
            return 2
            
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen = set()

    print(f"Starten van scan op {datetime.now()}")

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.text)
            
            count_found = 0
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                
                # STRENG OP DATUM CHECKEN
                if not is_recent(entry):
                    continue
                
                title = entry.get('title', '').strip()
                prio = get_prio_level(title, link, name)
                
                if prio > 0:
                    item = {'title': title, 'link': link, 'source': name}
                    if prio == 1:
                        all_prio1.append(item)
                    else:
                        all_prio2.append(item)
                    seen.add(link)
                    count_found += 1
            print(f"[{name}] {count_found} nieuwe artikelen gevonden.")
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
        print("Mail verstuurd!")
    else:
        print("Geen verse artikelen gevonden.")

if __name__ == "__main__":
    main()
