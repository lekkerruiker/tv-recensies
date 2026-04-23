import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# We gebruiken voor de Volkskrant een alternatieve URL-structuur die vaak beter werkt
FEEDS = {
    "Volkskrant": "https://www.volkskrant.nl/televisie/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
}

def get_prio_level(title, link, source):
    t, l = title.lower(), link.lower()
    
    # --- STAP 1: HARDE BLOCKS (Tegen de boek/concert vervuiling) ---
    # Als deze woorden erin staan, negeren we het ALTIJD (behalve als er 'tv' bij staat)
    blocks = ['boekrecensie', 'concertrecensie', 'theater', 'literatuur', 'popmuziek', 'album', 'roman']
    if any(x in t for x in blocks) and 'tv' not in t:
        return 0

    # --- STAP 2: PRIO 1 (De echte recensies) ---
    # Specifieke Volkskrant check: moet in televisie sectie zitten
    if source == "Volkskrant" and 'televisie' in l:
        return 1
        
    # VIP namen en secties voor andere kranten
    vip_names = ['han-lips', 'maaike-bos', 'peereboom', 'zap', 'lips-kijkt']
    if any(x in l for x in vip_names) or any(x in t for x in ['tv-recensie', 'zap:', 'bekeken:']):
        return 1

    # --- STAP 3: PRIO 2 (Media nieuws) ---
    # Gebruik \b voor hele woorden om 'inpoldering' te voorkomen
    media_words = [r'\btv\b', r'\btelevisie\b', r'\bnpo\b', r'\brtl\b', r'\bsbs\b', r'\bvideoland\b', r'\bnetflix\b', r'\bstreaming\b']
    if any(re.search(pattern, t) or re.search(pattern, l) for pattern in media_words):
        # Extra check om klimaat/politiek ruis in Prio 2 te voorkomen
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'asiel']):
            return 2
            
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen = set()

    print("Starten van de herstelde scan...")

    for name, url in FEEDS.items():
        try:
            # We downloaden de feed met een mobiele User-Agent (iPhone)
            # Dit omzeilt vaak de zware desktop-blokkades van de Volkskrant
            resp = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.text)
            
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                
                title = entry.get('title', '').strip()
                prio = get_prio_level(title, link, name)
                
                if prio > 0:
                    item = {'title': title, 'link': link, 'source': name}
                    if prio == 1:
                        all_prio1.append(item)
                    else:
                        all_prio2.append(item)
                    seen.add(link)
                    print(f"Gevonden [{name}]: {title}")
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
    else:
        print("Geen relevante artikelen gevonden.")

if __name__ == "__main__":
    main()
