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
    """Check of artikel van de laatste 48 uur is."""
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub: return True
    return datetime(*pub[:6]) >= (datetime.now() - timedelta(hours=48))

def get_prio_level(title, link, source):
    """Bepaalt de categorie. Retouneert 1 (Recensie), 2 (Nieuws), 3 (Overig) of 0 (Negeren)."""
    t = title.lower()
    l = link.lower()
    
    # --- STAP 1: VIP SELECTIE (Altijd Prio 1) ---
    # Als dit in de URL of titel staat, kijken we niet eens verder naar filters.
    if any(x in l for x in ['/televisie', '/zap', 'han-lips', 'maaike-bos', 'marcel-peereboom-voller']):
        return 1
    if any(x in t for x in ['tv-recensie', 'tv-column', 'han lips', 'maaike bos']):
        return 1

    # --- STAP 2: UITSLUITEN (De brij wegfilteren) ---
    # Alleen uitsluiten als het GEEN VIP is.
    if any(x in t for x in ['podcast', 'luisterboek', 'filmrecensie', 'theater', 'concert']):
        return 0

    # --- STAP 3: MEDIA CHECK (Prio 2 of 3) ---
    media_words = ['tv', 'televisie', 'kijkcijfers', 'npo', 'rtl', 'sbs', 'streaming', 'netflix', 'videoland', 'presentator', 'omroep', 'vandaag inside', 'jinek', 'beau', 'renze']
    if any(w in t or w in l for w in media_words):
        return 2 # Voorlopig 2, AI mag later verfijnen naar 3
        
    return 0

def scrape_feeds():
    results = {'prio1': [], 'potential': []}
    seen = set()
    
    for name, url in FEEDS.items():
        try:
            # We downloaden de feed handmatig om blokkades te voorkomen
            r = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(r.content)
            
            for entry in feed.entries:
                link = entry.get('link')
                if not link or link in seen: continue
                if not is_recent(entry): continue
                
                prio = get_prio_level(entry.get('title', ''), link, name)
                if prio > 0:
                    item = {'title': entry.get('title', '').strip(), 'link': link, 'source': name}
                    if prio == 1:
                        results['prio1'].append(item)
                    else:
                        results['potential'].append(item)
                    seen.add(link)
        except Exception as e:
            print(f"Fout bij {name}: {e}")
    return results

def classify_with_ai(articles):
    if not articles or not GEMINI_KEY:
        return {'prio2': articles, 'prio3': []}
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title']} for i, a in enumerate(articles)]
    
    prompt = (
        "Classificeer deze media-artikelen in 'prio2' (hard nieuws over TV/cijfers/zenders) "
        "of 'prio3' (achtergrond/interviews). Gooi irrelevante artikelen (boeken/politiek) weg. "
        f"JSON output: {{\"prio2\": [ids], \"prio3\": [ids]}}. Lijst: {json.dumps(input_data)}"
    )

    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
        raw = res.json()['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
        return {
            'prio2': [articles[i] for i in data.get('prio2', []) if i < len(articles)],
            'prio3': [articles[i] for i in data.get('prio3', []) if i < len(articles)]
        }
    except:
        return {'prio2': articles, 'prio3': []}

def build_section(title, items, color):
    if not items: return ""
    html = f"<h2 style='color:{color}; border-bottom:1px solid {color};'>{title} ({len(items)})</h2>"
    for art in items:
        html += f"<p><strong>[{art['source']}]</strong> {art['title']}<br>"
        html += f"<a href='{art['link']}'>Direct</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    return html

def main():
    data = scrape_feeds()
    ai_data = classify_with_ai(data['potential'])
    
    body = build_section("⭐ Recensies", data['prio1'], "#e67e22")
    body += build_section("📺 Media Nieuws", ai_data['prio2'], "#2980b9")
    body += build_section("🎧 Achtergrond", ai_data['prio3'], "#7f8c8d")
    
    if data['prio1'] or ai_data['prio2'] or ai_data['prio3']:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })

if __name__ == "__main__":
    main()
