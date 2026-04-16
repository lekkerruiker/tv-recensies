import requests
import re
import resend
import os
import sys
from datetime import datetime

# Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    print("FOUT: Ontbrekende API-sleutels of ontvanger.")
    sys.exit(1)

resend.api_key = API_KEY

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_gemini_summary(title, source):
    if not GEMINI_KEY:
        return "Voeg GEMINI_API_KEY toe."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"Analyseer titel: '{title}' van {source}. Relevant voor TV/media/series? Zo ja: 1 zin samenvatting NL. Zo nee: REJECT."
    
    try:
        response = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        response.raise_for_status() # Geeft fout als API-key niet werkt
        result = response.json()
        
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            print(f"Gemini gaf onverwachte output voor: {title}")
            return "Geen samenvatting."
    except Exception as e:
        print(f"Gemini Fout voor {title}: {e}")
        return "Samenvatting niet beschikbaar."

def get_reviews():
    results = []
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            content = resp.text
            items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
            
            for item in items:
                title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                link_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                
                if not link_match:
                    link_match = re.search(r'<guid.*?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</guid>', item, re.DOTALL)

                if title_match and link_match:
                    title = re.sub('<[^<]+?>', '', title_match.group(1).strip())
                    link = link_match.group(1).strip()

                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        summary = get_gemini_summary(title, name)
                        
                        if "REJECT" in summary.upper():
                            continue

                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 20px;'>
                            <strong style='font-size: 1.1em;'>[{name}] {title}</strong><br>
                            <div style='color: #444; border-left: 3px solid #3498db; padding-left: 10px; margin: 5px 0; font-style: italic;'>{summary}</div>
                            <a href='{archive_link}' style='color: #3498db; font-size: 0.9em;'>🔓 Lees artikel</a>
                        </li>""")
        except Exception as e:
            print(f"Fout bij feed {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    content = get_reviews()
    # We sturen de mail ALTIJD, zelfs als get_reviews een foutje bevat, om crash te voorkomen
    try:
        html_body = f"<html><body><h2>📺 Media Update</h2><ul>{content if content else '<li>Niets gevonden.</li>'}</ul></body></html>"
        resend.Emails.send({
            "from": EMAIL_FROM, "to": [EMAIL_RECEIVER],
            "subject": f"Media Update: {datetime.now().strftime('%d-%m')}", "html": html_body
        })
        print("Mail succesvol verstuurd.")
    except Exception as e:
        print(f"Resend Fout: {e}")
