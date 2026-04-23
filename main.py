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

# Kranten die wel goed gaan via RSS
RSS_FEEDS = {
    "Trouw": "https://www.trouw.nl/rss.xml",
    "NRC": "https://www.nrc.nl/rss/",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_dpg_via_ai():
    """Gebruikt Gemini om de nieuwste artikelen van Volkskrant en Parool te vinden."""
    if not GEMINI_KEY:
        print("Geen Gemini API Key gevonden!")
        return []
    
    prompt = """Zoek de 5 meest recente tv-recensies of media-artikelen van de Volkskrant en het Parool van gisteren of vandaag. 
    Focus op Han Lips (Parool) en Maaike Bos of de televisie-sectie (Volkskrant).
    Geef het resultaat terug in dit EXACTE JSON formaat:
    {"articles": [{"title": "...", "link": "...", "source": "Volkskrant of Parool"}]}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    try:
        res = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }, timeout=30)
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        return json.loads(raw_text).get('articles', [])
    except Exception as e:
        print(f"AI-zoekopdracht mislukt: {e}")
        return []

def main():
    all_articles = []
    seen = set()

    # 1. Haal Volkskrant & Parool op via de AI route
    print("Zoeken naar Volkskrant en Parool via AI...")
    ai_results = get_dpg_via_ai()
    for art in ai_results:
        all_articles.append(art)
        seen.add(art['link'])

    # 2. Haal de rest op via de vertrouwde RSS
    for name, url in RSS_FEEDS.items():
        try:
            print(f"Scannen: {name}...")
            feed = feedparser.parse(requests.get(url, timeout=15).text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                if not link or link in seen: continue
                
                # Check of het over media gaat
                if any(x in link.lower() or x in title.lower() for x in ['tv', 'recensie', 'zap', 'kijkt']):
                    all_articles.append({'title': title, 'link': link, 'source': name})
                    seen.add(link)
        except: continue

    # E-mail opbouw
    body = ""
    if all_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Media Selectie</h2>"
        for art in all_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body>{body}</body></html>"
            })
        print("Mail verzonden!")

if __name__ == "__main__":
    main()
