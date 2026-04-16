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
        return "Voeg GEMINI_API_KEY toe aan env in je YML bestand."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    Analyseer deze krantentitel: '{title}' van {source}.
    Is dit artikel relevant voor iemand die alleen geïnteresseerd is in TV, series, journalistiek of media?
    Zo ja: Geef een samenvatting van exact één zin in het Nederlands.
    Zo nee: Antwoord ALLEEN met het woord REJECT.
    """
    
    try:
        response = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "Samenvatting momenteel niet beschikbaar."

def get_reviews():
    results = []
    # Iets bredere keywords om de AI meer voer te geven
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'journalist']
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
                        if not any(link in r for r in results):
                            summary = get_gemini_summary(title, name)
                            
                            # Als de AI zegt dat het geen media is, overslaan!
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
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    html_body = f"""
    <html>
        <body style='font-family: sans-serif; line-height: 1.5; color: #333; max-width: 600px;'>
            <h2 style='color: #2c3e50;'>📺 Media Update</h2>
            <p style='color: #7f8c8d;'>Geselecteerd en samengevat door AI.</p>
            <hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>
            <ul style='list-style: none; padding: 0;'>{content if content else "<li>Geen media-nieuws gevonden vandaag.</li>"}</ul>
        </body>
    </html>
    """
    resend.Emails.send({
        "from": EMAIL_FROM, "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}", "html": html_body
    })

if __name__ == "__main__":
    send_mail(get_reviews())
