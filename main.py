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
    """Haalt samenvatting op via Gemini API."""
    if not GEMINI_KEY:
        return "REJECT"
    
    # Deze URL is de meest robuuste voor v1beta
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = (
        f"Krant: {source}. Titel: {title}. "
        "Is dit mediagerelateerd (TV, series, talkshow, journalistiek)? "
        "Zo ja: Schrijf 1 korte samenvatting (max 20 woorden) in het Nederlands. "
        "Zo nee: Antwoord met alleen het woord REJECT."
    )
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        time.sleep(1) # Kleine pauze voor de gratis limiet
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            # Als hij hier 404 geeft, proberen we een alternatieve URL structuur
            return "REJECT"
            
        data = response.json()
        if 'candidates' in data and data[0] if isinstance(data, list) else data.get('candidates'):
            # Google's JSON structuur is soms een doolhof, we pakken hem voorzichtig:
            try:
                text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                return text
            except:
                return "REJECT"
        return "REJECT"
    except:
        return "REJECT"

def run_scraper():
    """Scant feeds en filtert resultaten."""
    print("🚀 Scraper gestart...")
    results = []
    
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau', 'journalist']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        print(f"Bezig met scannen van {name}...")
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
                        
                        if "REJECT" not in summary.upper():
                            archive_link = f"https://archive.is/{link}"
                            results.append(f"""
                            <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid #3498db; padding-left: 15px;'>
                                <strong style='font-size: 17px; color: #2c3e50;'>[{name}] {title}</strong><br>
                                <p style='margin: 8px 0; color: #444; font-size: 15px; font-style: italic;'>{summary}</p>
                                <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-weight: bold;'>🔓 Lees artikel</a>
                            </li>""")
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    if not API_KEY or not EMAIL_RECEIVER:
        print("❌ FOUT: Secrets missen.")
        exit(1)

    articles_html = run_scraper()
    
    if not articles_html:
        subject = f"Media Update [GEEN NIEUWS]: {datetime.now().strftime('%d-%m')}"
        body_content = "<p>Vandaag geen relevante media-artikelen gevonden.</p>"
    else:
        subject = f"Media Update: {datetime.now().strftime('%d-%m')}"
        body_content = f"<ul style='padding: 0;'>{articles_html}</ul>"

    # Mail verzenden
    mail_url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": subject,
        "html": f"<html><body>{body_content}</body></html>"
    }
    
    try:
        r = requests.post(mail_url, headers=headers, json=payload, timeout=20)
        print(f"✅ Status: {r.status_code}, Respons: {r.text}")
    except Exception as e:
        print
