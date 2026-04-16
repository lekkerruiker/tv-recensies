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
    if not GEMINI_KEY:
        return "REJECT"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    # We maken de instructie iets minder streng
    prompt = (
        f"Krant: {source}. Titel: {title}. "
        "Is dit gerelateerd aan media, cultuur, TV, series, radio of journalistiek? "
        "Zo ja: Schrijf 1 korte samenvatting in NL. "
        "Zo nee: Antwoord met alleen het woord REJECT."
    )
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        time.sleep(1) 
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"DEBUG: Google API fout {response.status_code} voor: {title[:30]}")
            return "REJECT"
            
        data = response.json()
        if 'candidates' in data and data['candidates']:
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            # Log wat de AI besluit
            print(f"AI Besluit voor '{title[:40]}...': {text[:20]}")
            return text
        return "REJECT"
    except:
        return "REJECT"

def run_scraper():
    print("🚀 Scraper gestart...")
    results = []
    
    # Breder palet aan keywords
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'barend', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau', 'journalist', 'cultuur', 'film', 'programma']
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

                    # Als een van de keywords in de titel staat: check met AI
                    if any(k in title.lower() for k in KEYWORDS):
                        summary = get_gemini_summary(title, name)
                        
                        if "REJECT" not in summary.upper():
                            archive_link = f"https://archive.is/{link}"
                            results.append(f"""
                            <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid #3498db; padding-left: 15px;'>
                                <strong style='font-size: 17px;'>[{name}] {title}</strong><br>
                                <p style='margin: 8px 0; color: #444;'>{summary}</p>
                                <a href='{archive_link}' style='color: #3498db;'>🔓 Lees artikel</a>
                            </li>""")
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    articles_html = run_scraper()
    
    # We sturen de mail altijd.
    if not articles_html:
        subject = f"Media Update [GEEN NIEUWS]: {datetime.now().strftime('%d-%m')}"
        body_content = "<p>De AI heeft alle gevonden artikelen van vandaag als 'niet mediagerelateerd' beoordeeld.</p>"
    else:
        subject = f"Media Update: {datetime.now().strftime('%d-%m')}"
        body_content = f"<ul style='padding: 0;'>{articles_html}</ul>"

    mail_url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": subject,
        "html": f"<html><body>{body_content}</body></html>"
    }
    
    requests.post(mail_url, headers=headers, json=payload, timeout=20)
    print("✅ Proces voltooid.")
