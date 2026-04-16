import requests
import re
import resend
import os
import sys
from datetime import datetime
import time

# Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

resend.api_key = API_KEY

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_gemini_summary(title, source):
    if not GEMINI_KEY: return "Sleutel ontbreekt."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"Analyseer krantentitel: '{title}' van {source}. Is dit mediagerelateerd (TV, series, journalistiek, talkshows)? Zo ja: 1 korte zin samenvatting NL. Zo nee: REJECT."
    
    try:
        time.sleep(1) # Voorkom rate limits
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "Geen samenvatting (AI fout)."

def get_reviews():
    results = []
    # Iets ruimere keywords om de AI te laten beslissen
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside']
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
                        
                        # Alleen REJECT als de AI het echt zeker weet
                        if "REJECT" in summary.upper() and len(summary) < 10:
                            continue

                        archive_link = f"https://archive.is/{link}"
                        results.append(f"<li style='margin-bottom:15px;'><strong>[{name}] {title}</strong><br><div style='color:#555;'>{summary}</div><a href='{archive_link}'>Lees artikel</a></li>")
        except:
            continue
            
    return "".join(results)

if __name__ == "__main__":
    content = get_reviews()
    
    # Als content leeg is, sturen we een 'test' bericht om te zien of Resend werkt
    final_content = content if content else "<li>Geen media-artikelen gevonden met de huidige filters.</li>"
    status = "SUCCESS" if content else "LEEG"

    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"Media Update [{status}]: {datetime.now().strftime('%d-%m')}",
            "html": f"<html><body><h2>📺 Update</h2><ul>{final_content}</ul></body></html>"
        })
        print("✅ Script voltooid en mail verzonden.")
    except Exception as e:
        print(f"❌ Mail verzenden mislukt: {e}")
