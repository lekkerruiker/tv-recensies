import os
import requests
import feedparser
from datetime import datetime, timedelta
import json
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
    return datetime(*pub[:6]) >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link):
    t = title.lower()
    l = link.lower()
    
    # --- 1. VIP RECHTSSTREEKSE MATCHES (Recensies) ---
    # We kijken naar URL-paden die specifiek voor TV-recensies zijn
    if any(x in l for x in ['/televisie', '/zap', 'han-lips', 'maaike-bos', 'peereboom']):
        return 1
    # Specifieke titels die op recensies duiden
    if any(x in t for x in ['tv-recensie', 'han lips', 'maaike bos', 'zap:', 'bekeken:']):
        return 1

    # --- 2. HARD BLOCK (Voorkomen van ruis) ---
    # Als deze woorden erin staan, negeren we het (tenzij het een VIP hierboven was)
    exclude_words = ['klimaat', 'ecb', 'politiek', 'polder', 'asiel', 'oorlog', 'economie']
    if any(x in t for x in exclude_words):
        return 0

    # --- 3. STRIKTE MEDIA CHECK (Geen Scunthorpe meer) ---
    # We gebruiken r'\bword\b' om te zorgen dat het hele woorden zijn
    # Dus 'NPO' matcht niet in 'inpoldering'
    strict_keywords = [
        r'\btv\b', r'\btelevisie\b', r'\bnpo\b', r'\brtl\b', r'\bsbs\b', 
        r'\bvideoland\b', r'\bnetflix\b', r'\bstreaming\b', r'\bkijkcijfer',
        r'\bpresentator\b', r'\bomroep\b', r'\bjinek\b', r'\blubach\b'
    ]
    
    for pattern in strict_keywords:
        if re.search(pattern, t) or re.search(pattern, l):
            # Als Mr. Frank Visser erin staat, is het Prio 2 (zoals je voorbeeld)
            if 'frank visser' in t:
                return 2
            return 2
            
    return 0

def main():
    print("Starten van scraper met strikte filters...")
    all_articles = {'prio1': [], 'potential': []}
    seen = set()
    
    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}")
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.content)
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
        except Exception as e:
            print(f"Fout bij {name}: {e}")

    # E-mail genereren
    body = ""
    sections = [
        ('prio1', '⭐ Dagelijkse Recensies', '#e67e22'),
        ('potential', '📺 Media Nieuws', '#2980b9')
    ]
    
    for level, section_title, color in sections:
        if all_articles[level]:
            body += f"<h2 style='color:{color}; border-bottom:1px solid {color}; padding-bottom:5px;'>{section_title}</h2>"
            for art in all_articles[level]:
                body += f"<div style='margin-bottom:15px;'><strong>[{art['source']}]</strong> {art['title']}<br>"
                body += f"<a href='{art['link']}' style='color:#3498db;'>Lees artikel</a> | "
                body += f"<a href='https://archive.is/{art['link']}' style='color:#7f8c8d;'>🔓 Archief</a></div>"

    if body:
        print("Mail versturen...")
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:Arial, sans-serif; line-height:1.6; max-width:600px;'>{body}</body></html>"
            })
        print("Klaar!")
    else:
        print("Geen relevante artikelen gevonden vandaag.")

if __name__ == "__main__":
    main()
