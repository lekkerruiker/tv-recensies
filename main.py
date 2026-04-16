import os
import requests
import re
from datetime import datetime
import time

# 1. Instellingen - Gebruik exacte namen uit de omgeving
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
    if not GEMINI_KEY:
        return "AI samenvatting niet beschikbaar."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"Analyseer deze krantentitel: '{title}' van {source}. Is dit relevant voor TV, media, series of journalistiek? Zo ja: geef 1 korte samenvatting in het Nederlands. Zo nee: antwoord alleen met het woord REJECT."
    
    try:
        time.sleep(1) 
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        result = resp.json()
        # Controleer of de structuur van de respons klopt
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text'].strip()
        return "Geen samenvatting beschikbaar."
    except Exception as e:
        print(f"AI Fout voor {title}: {e}")
        return "Samenvatting mislukt."

def run_scraper():
    print("--- START MEDIA SCRAPER ---")
    results = []
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside', 'beau', 'renze', 'eva jinek']
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
                        
                        # Filter op REJECT
                        if "REJECT" in summary.upper() and len(summary) < 20:
                            continue

                        archive_link = f"https://archive.is/{link}"
                        results.append(f"<li style='margin-bottom:20px;'><strong style='font-size:16px;'>[{name}] {title}</strong><br><p style='color:#444; margin:5px 0;'>{summary}</p><a href='{archive_link}' style='color:#007bff;'>🔓 Lees via Archive.is</a></li>")
        except Exception as e:
            print(f"Fout bij feed {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    # Check of de belangrijkste keys er zijn voor we starten
    if not API_KEY or not EMAIL_RECEIVER:
        print("❌ CRITIEKE FOUT: API_KEY of EMAIL_RECEIVER ontbreekt.")
        exit(1)

    content = run_scraper()
    
    if not content:
        content = "<li>Geen media-artikelen gevonden vandaag die door de AI-selectie kwamen.</li>"

    # Mail versturen
    url = "https://api.resend.com/emails"
    payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"<html><body style='font-family:Arial, sans-serif; max-width:600px;'><h2>📺 Media Update</h2><hr><ul style='list-style:none; padding:0;'>{content}</ul></body></html>"
    }
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code in [200, 201]:
            print(f"✅ Mail succesvol verzonden! ID: {response.json().get('id')}")
        else:
            print(f"❌ Mail fout {response.status_code}: {response.text}")
            exit(1)
    except Exception as e:
        print(f"❌ Systeemfout bij verzenden: {e}")
        exit(1)
