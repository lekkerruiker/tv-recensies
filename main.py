import os
import requests
import re
from datetime import datetime
import time

# --- CONFIGURATIE ---
# Deze namen moeten EXACT overeenkomen met de namen in je daily.yml (env gedeelte)
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
    """Haalt samenvatting op via de gratis Gemini 1.5 Flash API."""
    if not GEMINI_KEY:
        return "REJECT"
    
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
        # Pauze om 'Rate Limits' van de gratis API te voorkomen
        time.sleep(2) 
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"⚠️ Google API Fout {response.status_code} voor '{title}'")
            return "REJECT"
            
        data = response.json()
        if 'candidates' in data and data['candidates']:
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            return text
        return "REJECT"
    except Exception as e:
        print(f"❌ AI Systeemfout voor '{title}': {e}")
        return "REJECT"

def run_scraper():
    """Scant alle RSS feeds en filtert ze via de AI."""
    print("🚀 Scraper gestart...")
    results = []
    
    # Eerste snelle selectie op trefwoorden om AI-tegoed te sparen
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau', 'journalist']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        print(f"Bezig met scannen van {name}...")
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # Vind alle items in de RSS feed
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = re.sub('<[^<]+?>', '', t_match.group(1).strip())
                    link = l_match.group(1).strip()

                    # Check trefwoorden
                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        # Laat AI bepalen of het echt relevant is
                        summary = get_gemini_summary(title, name)
                        
                        # Alleen toevoegen als de AI niet 'REJECT' antwoordt
                        if "REJECT" not in summary.upper():
                            archive_link = f"https://archive.is/{link}"
                            results.append(f"""
                            <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid #3498db; padding-left: 15px;'>
                                <strong style='font-size: 17px; color: #2c3e50;'>[{name}] {title}</strong><br>
                                <p style='margin: 8px 0; color: #444; font-size: 15px; font-style: italic;'>{summary}</p>
                                <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-weight: bold;'>🔓 Lees artikel via Archive.is</a>
                            </li>""")
        except Exception as e:
            print(f"⚠️ Fout bij feed {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    # Check kritieke variabelen
    if not API_KEY or not EMAIL_RECEIVER:
        print("❌ CRITIEKE FOUT: RESEND_API_KEY of EMAIL_RECEIVER ontbreekt in GitHub Secrets.")
        exit(1)

    articles_html = run_scraper()
    
    # Stel de mail samen (altijd mailen voor bevestiging)
    if not articles_html:
        final_body = "<p style='color: #666;'>De scraper heeft gedraaid, maar er zijn geen media-artikelen gevonden die de AI-selectie hebben doorstaan.</p>"
        subject = f"Media Update [GEEN NIEUWS]: {datetime.now().strftime('%d-%m')}"
    else:
        final_body = f"<ul style='padding: 0;'>{articles_html}</ul>"
        subject = f"Media Update: {datetime.now().strftime('%d-%m')}"

    # Mail verzenden via Resend API (Directe HTTP request voor maximale stabiliteit)
    mail_url = "https://api.resend.com/emails"
    mail
