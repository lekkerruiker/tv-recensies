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
    """Vraagt Gemini om een samenvatting van één zin op basis van de titel en bron."""
    if not GEMINI_KEY:
        return "Voeg GEMINI_API_KEY toe voor AI samenvattingen."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"Geef een samenvatting van maximaal één zin voor een artikel van de krant {source} met de titel: '{title}'. Als de titel over een TV-programma of serie gaat, vermeld dan kort welk programma het is. Antwoord in het Nederlands."
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "Samenvatting tijdelijk niet beschikbaar."

def get_reviews():
    results = []
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp']
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

                    combined_text = (title + " " + link).lower()
                    if any(k in combined_text for k in KEYWORDS):
                        if not any(link in r for r in results):
                            # AI om hulp vragen
                            summary = get_gemini_summary(title, name)
                            archive_link = f"https://archive.is/{link}"
                            
                            results.append(f"""
                            <li style='margin-bottom: 20px;'>
                                <strong style='font-size: 1.1em;'>[{name}] {title}</strong><br>
                                <div style='color: #444; border-left: 3px solid #3498db; padding-left: 10px; margin: 5px 0;'>{summary}</div>
                                <a href='{archive_link}' style='color: #3498db; font-size: 0.9em;'>🔓 Lees volledig artikel via Archive.is</a>
                            </li>""")
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    html_body = f"""
    <html>
        <body style='font-family: -apple-system, sans-serif; line-height: 1.5; color: #333; max-width: 600px;'>
            <h2 style='color: #2c3e50;'>📺 Jouw Media Update</h2>
            <p style='color: #7f8c8d; font-size: 0.9em;'>De belangrijkste TV- en media-artikelen van vandaag, samengevat door AI.</p>
            <hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>
            <ul style='list-style: none; padding: 0;'>
                {content if content else "<li>Geen media-artikelen gevonden vandaag.</li>"}
            </ul>
        </body>
    </html>
    """
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": html_body,
    })

if __name__ == "__main__":
    send_mail(get_reviews())
