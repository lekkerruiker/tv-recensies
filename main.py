import os
import requests
import re
from datetime import datetime
import time

# Instellingen
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
        return "REJECT"
    
    # De specifieke URL voor de gratis Gemini 1.5 Flash API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = (
        f"Krant: {source}. Titel: {title}. "
        "Is dit mediagerelateerd (TV, series, talkshow, journalistiek)? "
        "Zo ja: Schrijf 1 korte samenvatting (max 20 woorden) in NL. "
        "Zo nee: Antwoord alleen met REJECT."
    )
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        # Wacht even tussen verzoeken voor de gratis API limiet
        time.sleep(2) 
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"⚠️ Google API Fout {response.status_code}: {response.text}")
            return "REJECT"
            
        data = response.json()
        # Navigeer veilig door de Google JSON structuur
        if 'candidates' in data and data['candidates']:
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            return text
        return "REJECT"
    except Exception as e:
        print(f"❌ AI Systeemfout: {e}")
        return "REJECT"

def run_scraper():
    print("🚀 Starten met scannen van feeds...")
    results = []
    # Keywords die wijzen op media/TV content
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau']
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

                    # Stap 1: Filter op trefwoorden
                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        # Stap 2: Laat AI beslissen en samenvatten
                        summary = get_gemini_summary(title, name)
                        
                        # Alleen toevoegen als AI het relevant vindt (geen REJECT)
                        if "REJECT" not in summary.upper():
                            archive_link = f"https://archive.is/{link}"
                            results.append(f"""
                            <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid #3498db; padding-left: 15px;'>
                                <strong style='font-size: 17px;'>[{name}] {title}</strong><br>
                                <p style='margin: 8px 0; color: #444; font-size: 15px;'>{summary}</p>
                                <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-weight: bold;'>🔓 Lees artikel</a>
                            </li>""")
        except Exception as e:
            print(f"⚠️ Feed fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    articles_html = run_scraper()
    
    if not articles_html:
        print("Geen relevante media-artikelen gevonden vandaag.")
        # We sturen geen lege mail om je Resend-limiet te sparen
    else:
        # Mail versturen via Resend
        mail_payload = {
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
            "html": f"<html><body style='font-family: Arial, sans-serif; max-width: 600px;'><h2>📺 Media & TV Overzicht</h2><hr>{articles_html}</body></html>"
        }
        
        try:
            r = requests.post(
                "https://api.resend.com/emails", 
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json=mail_payload, 
                timeout=15
            )
            print(f"✅ Mail status: {r.status_code}")
        except Exception as e:
            print(f"❌ Mail fout: {e}")
