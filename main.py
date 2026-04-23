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

# Terug naar de stabiele basis voor de overige kranten
RSS_FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "NRC": "https://www.nrc.nl/rss/",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_dpg_via_ai():
    """Laat Gemini specifiek in het archief van de Volkskrant en Parool zoeken."""
    if not GEMINI_KEY:
        return []
    
    gisteren = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    prompt = f"""Kijk naar de Volkskrant archiefpagina van gisteren: https://www.volkskrant.nl/archief/{gisteren}
    En de televisie sectie van het Parool: https://www.parool.nl/televisie
    
    Selecteer alleen echte media-artikelen:
    1. TV-recensies (Han Lips, Maaike Bos, etc.)
    2. Artikelen over talkshows, series of streamingdiensten.
    3. Verwijder alle ruis (geen sport, geen algemeen nieuws, geen kerkdiensten).
    
    Antwoord in dit JSON formaat:
    {{"articles": [{"title": "...", "link": "...", "source": "..."}]}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    try:
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }, timeout=30)
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        return json.loads(raw_text).get('articles', [])
    except Exception as e:
        print(f"AI Search fout: {e}")
        return []

def get_prio_level_strict(title, link):
    """De oude vertrouwde strenge filter tegen het Scunthorpe-probleem."""
    t, l = title.lower(), link.lower()
    
    # VIP namen (Prio 1)
    if any(x in l for x in ['han-lips', 'maaike-bos', 'peereboom', 'zap']):
        return 1
    
    # Media-specifieke titels (Prio 1)
    if any(x in t for x in ['tv-recensie', 'zap:', 'bekeken:']):
        return 1

    # Strikte Media Check (Prio 2)
    # Alleen als 'tv' of 'npo' als los woord voorkomt, niet midden in een woord
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming)\b', t):
        # Harde uitsluitingen voor niet-relevante context
        if not any(x in t for x in ['stikstof', 'oekraïne', 'kerkdienst', 'sport', 'voetbal', 'beurs']):
            return 2
            
    return 0

def main():
    all_articles = []
    seen = set()

    # 1. Volkskrant & Parool via AI-Archief check
    print("AI checkt Volkskrant archief en Parool TV...")
    ai_results = get_dpg_via_ai()
    for art in ai_results:
        all_articles.append(art)
        seen.add(art['link'])

    # 2. Andere kranten via STRENGE RSS
    for name, url in RSS_FEEDS.items():
        try:
            print(f"Scannen: {name}...")
            feed = feedparser.parse(requests.get(url, timeout=15).text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                if not link or link in seen: continue
                
                prio = get_prio_level_strict(title, link)
                if prio > 0:
                    all_articles.append({'title': title, 'link': link, 'source': name})
                    seen.add(link)
        except: continue

    # E-mail opbouw
    body = ""
    if all_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in all_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print("Klaar!")

if __name__ == "__main__":
    main()
