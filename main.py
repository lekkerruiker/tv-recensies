import os
import requests
import feedparser
from datetime import datetime, timedelta
import json
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
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
    # We kijken 48 uur terug
    return datetime(*pub[:6]) >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link):
    t = title.lower()
    l = link.lower()
    
    # VIP check (Recensies)
    if any(x in l for x in ['/televisie', '/zap', 'han-lips', 'maaike-bos', 'peereboom']):
        return 1
    if any(x in t for x in ['tv-recensie', 'han lips', 'maaike bos', 'zap:']):
        return 1

    # Media algemeen
    media_keywords = ['tv', 'televisie', 'kijkcijfer', 'npo', 'rtl', 'sbs', 'streaming', 'netflix', 'videoland', 'omroep', 'vandaag inside']
    if any(w in t or w in l for w in media_keywords):
        return 2
        
    return 0

def main():
    print("Bezig met ophalen van feeds...")
    all_articles = {'prio1': [], 'potential': []}
    seen = set()
    
    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}")
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.content)
            count = 0
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                if not is_recent(entry): continue
                
                prio = get_prio_level(entry.get('title', ''), link)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1:
                        all_articles['prio1'].append(item)
                    else:
                        all_articles['potential'].append(item)
                    seen.add(link)
                    count += 1
            print(f"  Gevonden: {count} relevante artikelen")
        except Exception as e:
            print(f"  Fout bij {name}: {e}")

    # E-mail opbouwen
    body = ""
    for level, title, color in [('prio1', '⭐ Recensies', '#e67e22'), ('potential', '📺 Media Nieuws', '#2980b9')]:
        if all_articles[level]:
            body += f"<h2 style='color:{color}; border-bottom:1px solid {color};'>{title}</h2>"
            for art in all_articles[level]:
                body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        print("Mail versturen via Resend...")
        res = requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM,
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print(f"Resend response: {res.status_code}")
    else:
        print("Niets gevonden om te versturen.")

if __name__ == "__main__":
    main()
