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
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def is_recent(entry):
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: return True
    # Ruime marge van 48 uur om niets te missen
    return datetime(*pub[:6]) >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link, source):
    t, l = title.lower(), link.lower()
    
    # --- VOLKSKRANT SPECIFIEKE LOGICA (De variant die werkte) ---
    if source == "Volkskrant":
        # De Volkskrant zet recensies ALTIJD in deze URL-paden
        if any(x in l for x in ['/televisie', '/columns-opinie', 'han-lips', 'maaike-bos']):
            # Extra check: we willen geen algemene opinie, alleen media-gerelateerd
            if any(x in t or x in l for x in ['tv', 'recensie', 'lips', 'bos', 'kijk', 'serie', 'docu']):
                return 1

    # --- ALGEMENE LOGICA (Voor alle kranten) ---
    # VIP namen en secties
    if any(x in l for x in ['/zap', 'han-lips', 'maaike-bos', 'peereboom']):
        return 1
    if any(x in t for x in ['tv-recensie', 'han lips', 'maaike bos', 'zap:', 'bekeken:']):
        return 1

    # Media Nieuws (Prio 2) - Met de strikte \b (boundary) tegen 'inpoldering'
    strict_keywords = [r'\btv\b', r'\btelevisie\b', r'\bnpo\b', r'\brtl\b', r'\bsbs\b', r'\bomroep\b', r'\bkijkcijfer']
    if any(re.search(pattern, t) or re.search(pattern, l) for pattern in strict_keywords):
        # Filter ruis uit Prio 2
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'beurs']):
            return 2
            
    return 0

def main():
    print("Starten van scraper...")
    all_articles = {'prio1': [], 'potential': []}
    seen = set()
    
    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}")
            # ESSENTIEEL: Eerst ophalen met requests, dan pas parsen
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.encoding = 'utf-8'
            feed = feedparser.parse(response.text)
            
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                if not is_recent(entry): continue
                
                title = entry.get('title', '').strip()
                prio = get_prio_level(title, link, name)
                
                if prio > 0:
                    item = {'title': title, 'link': link, 'source': name}
                    if prio == 1:
                        all_articles['prio1'].append(item)
                    else:
                        all_articles['potential'].append(item)
                    seen.add(link)
                    print(f"  + [{name}] Gevonden: {title[:50]}...")
        except Exception as e:
            print(f"  - Fout bij {name}: {e}")

    # E-mail genereren
    body = ""
    if all_articles['prio1']:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Recensies</h2>"
        for art in all_articles['prio1']:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    
    if all_articles['potential']:
        body += "<h2 style='color:#2980b9; border-bottom:1px solid #2980b9;'>📺 Media Nieuws</h2>"
        for art in all_articles['potential']:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        print("Mail versturen...")
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
    else:
        print("Niets gevonden.")

if __name__ == "__main__":
    main()
