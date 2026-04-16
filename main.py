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

def get_gemini_summary(title, source):
    """Haalt samenvatting op of geeft None bij weigering/fout."""
    if not GEMINI_KEY: return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        f"Titel: {title}. Bron: {source}. "
        "Vat dit artikel over media/TV kort samen in 1 zin Nederlands. "
        "Als het echt niet over media gaat, antwoord alleen met 'REJECT'."
    )
    
    try:
        # Iets kortere pauze, maar wel aanwezig
        time.sleep(0.5)
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        if response.status_code == 200:
            text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return None if "REJECT" in text.upper() else text
    except:
        pass
    return None

def run_scraper():
    print("🚀 Scraper start...")
    results = []
    seen_links = set()
    
    # Uitgebreide lijst keywords
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'barend', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau', 'journalist', 'presentator']
    
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

                    # STAP 1: Keyword check
                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        # STAP 2: Probeer AI
                        summary = get_gemini_summary(title, name)
                        
                        # STAP 3: Fallback - Als AI 'REJECT' zegt maar het keyword is erg sterk, sturen we het TOCH door
                        if not summary:
                            # Alleen doorsturen zonder samenvatting als het keyword echt 'media-achtig' is
                            strong_keywords = ['sonja', 'borsato', 'recensie', 'televisie', 'tv-', 'vandaag inside']
                            if any(sk in title.lower() for sk in strong_keywords):
                                summary = "Nieuwsbericht over media/TV."
                            else:
                                continue

                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 20px; list-style: none; border-left: 3px solid #e67e22; padding-left: 10px;'>
                            <strong style='color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 5px 0; color: #666; font-size: 14px;'>{summary}</p>
                            <a href='{archive_link}' style='color: #e67e22; font-size: 13px;'>🔓 Lees artikel</a>
                        </li>""")
                        seen_links.add(link)
        except:
            continue
            
    return "".join(results)

if __name__ == "__main__":
    articles_html = run_scraper()
    
    # We forceren een resultaat voor de test
    if not articles_html:
        subject = f"Media Update [GEEN NIEUWS]: {datetime.now().strftime('%d-%m')}"
        body = "<p>Geen nieuwe artikelen gevonden in de RSS-feeds met de huidige trefwoorden.</p>"
    else:
        subject = f"Media Update: {datetime.now().strftime('%d-%m')}"
        body = f"<ul style='padding: 0;'>{articles_html}</ul>"

    # Verzenden
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": subject, "html": f"<html><body>{body}</body></html>"},
        timeout=20
    )
    print("✅ Klaar.")
