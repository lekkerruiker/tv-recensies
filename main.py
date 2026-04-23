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

RSS_FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "NRC": "https://www.nrc.nl/rss/",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_dpg_via_ai():
    """Laat Gemini specifiek in het archief van de Volkskrant en Parool zoeken."""
    if not GEMINI_KEY:
        print("Geen Gemini API Key gevonden!")
        return []
    
    # Gebruik gisteren voor het archief
    gisteren_dt = datetime.now() - timedelta(days=1)
    gisteren_str = gisteren_dt.strftime('%Y/%m/%d')
    
    # LET OP: Dubbele accolades {{ }} worden gebruikt om Python te laten weten 
    # dat dit tekst is en geen variabelen.
    prompt = f"""Kijk naar de Volkskrant archiefpagina van gisteren: https://www.volkskrant.nl/archief/{gisteren_str}
    En de televisie sectie van het Parool: https://www.parool.nl/televisie
    
    Selecteer alleen echte media-artikelen van de afgelopen 24-48 uur:
    1. TV-recensies (zoals van Han Lips of Maaike Bos).
    2. Artikelen over talkshows, series of streamingdiensten.
    3. Verwijder alle ruis (geen sport, geen algemeen nieuws, geen kerkdiensten).
    
    Antwoord in dit JSON formaat:
    {{
        "articles": [
            {{"title": "titel van artikel", "link": "volledige url", "source": "Volkskrant of Parool"}}
        ]
    }}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    try:
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }, timeout=30)
        
        data = res.json()
        if 'candidates' in data:
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw_text).get('articles', [])
        else:
            print(f"Gemini API Error: {data}")
            return []
    except Exception as e:
        print(f"AI Search fout: {e}")
        return []

def get_prio_level_strict(title, link):
    """Strenge filter tegen het Scunthorpe-probleem."""
    t, l = title.lower(), link.lower()
    
    # VIP namen (Prio 1)
    if any(x in l for x in ['han-lips', 'maaike-bos', 'peereboom', 'zap']):
        return 1
    
    if any(x in t for x in ['tv-recensie', 'zap:', 'bekeken:']):
        return 1

    # Strikte Media Check (Prio 2)
    if re.search(r'\b(tv|npo|rtl|sbs|videoland|netflix|streaming)\b', t):
        if not any(x in t for x in ['stikstof', 'oekraïne', 'kerkdienst', 'sport', 'voetbal', 'beurs']):
            return 2
            
    return 0

def main():
    all_articles = []
    seen = set()

    # 1. Volkskrant & Parool via AI
    print("AI checkt Volkskrant archief en Parool TV...")
    ai_results = get_dpg_via_ai()
    for art in ai_results:
        # Zorg dat links van AI altijd volledig zijn
        link = art.get('link', '')
        if link and link not in seen:
            all_articles.append(art)
            seen.add(link)

    # 2. Andere kranten via RSS
    for name, url in RSS_FEEDS.items():
        try:
            print(f"Scannen: {name}...")
            r = requests.get(url, timeout=15)
            feed = feedparser.parse(r.text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                if not link or link in seen: continue
                
                prio = get_prio_level_strict(title, link)
                if prio > 0:
                    all_articles.append({'title': title, 'link': link, 'source': name})
                    seen.add(link)
        except Exception as e:
            print(f"Fout bij {name}: {e}")

    # E-mail opbouw
    body = ""
    if all_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in all_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        response = requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print(f"E-mail status: {response.status_code}")
    else:
        print("Geen relevante artikelen gevonden.")

if __name__ == "__main__":
    main()
