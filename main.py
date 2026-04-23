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
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_volkskrant_via_gemini():
    """Haalt de tag-pagina op en laat Gemini de relevante TV-artikelen eruit vissen."""
    url = "https://www.volkskrant.nl/tag/televisie"
    articles = []
    try:
        print("Scannen van Volkskrant Tag-pagina...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        # We halen alle links en titels uit de HTML met een simpele regex
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?><h[^>]*>(.*?)</h', r.text, re.DOTALL)
        
        candidates = []
        for link, title in matches[:15]: # De laatste 15 artikelen
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            candidates.append({"title": clean_title, "link": f"https://www.volkskrant.nl{link}"})

        if not candidates or not GEMINI_KEY:
            return []

        # Gemini vragen om te filteren
        prompt = f"""Hieronder staat een lijst met artikelen van de Volkskrant tag-pagina 'televisie'. 
        Selecteer ALLEEN de artikelen die echt gaan over TV-recensies, TV-programma's, talkshows of streaming (zoals Netflix/Videoland).
        Verwijder artikelen over boeken, algemene politiek, sport (tenzij het over de uitzending gaat) of klimaat.
        
        ARTIKELEN:
        {json.dumps(candidates)}
        
        Antwoord in EXACT dit JSON formaat:
        {{"selected": [{"title": "...", "link": "..."}]}}"""

        gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        res = requests.post(gem_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        # JSON opschonen van markdown backticks
        clean_json = re.search(r'\{.*\}', raw_text, re.DOTALL).group()
        articles = json.loads(clean_json).get('selected', [])
        
        for a in articles: a['source'] = 'Volkskrant'
        print(f"  Gemini heeft {len(articles)} relevante VK artikelen gevonden.")
    except Exception as e:
        print(f"Fout bij Volkskrant/Gemini check: {e}")
    return articles

def get_prio_level(title, link):
    t, l = title.lower(), link.lower()
    # Prio 1 voor bekende secties en namen
    if any(x in l for x in ['/zap', 'han-lips', 'maaike-bos', 'peereboom']): return 1
    if any(x in t for x in ['tv-recensie', 'han lips', 'maaike bos', 'zap:', 'bekeken:']): return 1
    # Prio 2 voor algemeen media nieuws
    if re.search(r'\b(tv|televisie|npo|rtl|sbs|videoland|netflix|streaming|omroep)\b', t):
        if not any(x in t for x in ['klimaat', 'ecb', 'polder', 'boek']): return 2
    return 0

def main():
    all_prio1 = []
    all_prio2 = []
    seen_links = set()

    # 1. Volkskrant via de slimme route
    vk_results = get_volkskrant_via_gemini()
    for art in vk_results:
        all_prio1.append(art) # Alles van de TV-tag mag naar Prio 1
        seen_links.add(art['link'])

    # 2. De rest via RSS
    for name, url in FEEDS.items():
        try:
            print(f"Scannen: {name}...")
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen_links: continue
                prio = get_prio_level(entry.get('title', ''), link)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1: all_prio1.append(item)
                    else: all_prio2.append(item)
                    seen_links.add(link)
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
        print("Mail verzonden met succes!")

if __name__ == "__main__":
    main()
