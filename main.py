import os
import requests
import re
from datetime import datetime
import time

# 1. Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev" # Verplicht voor gratis Resend accounts

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_gemini_summary(title, source):
    if not GEMINI_KEY:
        return "AI samenvatting niet beschikbaar."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"Analyseer deze krantentitel: '{title}' van {source}. Is dit relevant voor TV/media/series? Zo ja: 1 korte zin samenvatting in NL. Zo nee: antwoord alleen met REJECT."
    
    try:
        time.sleep(1) # Voorkom dat we te snel gaan voor de gratis AI
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        result = resp.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "Geen samenvatting beschikbaar."

def run_scraper():
    print("--- START MEDIA SCRAPER ---")
    results = []
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = re.sub('<[^<]+?>', '', t_match.group(1).strip())
                    link = l_match.group(1).strip()

                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        summary = get_gemini_summary(title, name)
                        
                        if "REJECT" in summary.upper() and len(summary) < 15:
                            continue

                        archive_link = f"https://archive.is/{link}"
                        results.append(f"<li style='margin-bottom:20px;'><strong>[{name}] {title}</strong><br><em style='color:#555;'>{summary}</em><br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li>")
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    if not content:
        content = "<li>Geen media-artikelen gevonden vandaag.</li>"

    # Mail versturen via Requests (meest betrouwbaar)
    payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"<html><body style='font-family:sans-serif;'><h2>📺 Media Update</h2><ul>{content}</ul></body></html>"
    }
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://
