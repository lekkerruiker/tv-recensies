import os
import requests
import re
from datetime import datetime
import time

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_gemini_summary(title):
    """Directe en simpele aanroep naar Gemini."""
    if not GEMINI_KEY: return "AI Sleutel mist."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    # We vragen de AI om HEEL simpel te antwoorden
    prompt = f"Vat deze krantentitel kort samen in het Nederlands: '{title}'. Als het niet over media/TV/cultuur gaat, antwoord dan met het woord REJECT."
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        # De gratis tier heeft rust nodig
        time.sleep(2)
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        
        # De meest directe manier om de tekst te pakken
        tekst = data['candidates'][0]['content']['parts'][0]['text'].strip()
        return tekst
    except Exception as e:
        print(f"AI Fout voor {title[:20]}: {e}")
        return "Geen samenvatting beschikbaar."

def run_scraper():
    print("🚀 Scraper start...")
    results = []
    seen_links = set()
    
    # Brede lijst keywords om artikelen te vangen
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau', 'journalist', 'film', 'netflix', 'videoland']
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = re.sub('<[^<]+?>', '', t_match.group(1).strip())
                    link = l_match.group(1).strip()

                    if link in seen_links: continue

                    # Alleen verwerken als keyword matcht
                    if any(k in title.lower() for k in KEYWORDS):
                        summary = get_gemini_summary(title)
                        
                        # Alleen REJECT als de AI dat expliciet zegt
                        if "REJECT" in summary.upper() and len(summary) < 10:
                            continue

                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 20px; list-style: none; border-left: 3px solid #3498db; padding-left: 10px;'>
                            <strong style='color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 5px 0; color: #555; font-size: 14px;'>{summary}</p>
                            <a href='{archive_link}' style='color: #3498db;'>🔓 Lees artikel</a>
                        </li>""")
                        seen_links.add(link)
        except:
            continue
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    if not content:
        content = "<p>Geen media-artikelen gevonden vandaag.</p>"

    # Mail verzenden
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM, 
            "to": [EMAIL_RECEIVER], 
            "subject": f"Media Update: {datetime.now().strftime('%d-%m')}", 
            "html": f"<html><body><h2>📺 Media Update</h2>{content}</body></html>"
        },
        timeout=20
    )
    print("✅ Klaar.")
