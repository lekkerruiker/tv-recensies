import os
import requests
import re
from datetime import datetime
import time

# 1. Instellingen
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
        return "AI Key niet gevonden."
    
    # Gebruik de v1beta endpoint (vaak stabieler voor eenvoudige API-keys)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = f"Analyseer de krantentitel: '{title}' van {source}. Gaat dit over TV, series, media of journalistiek? Zo ja: geef een samenvatting van precies 1 zin in het Nederlands. Zo nee: antwoord met alleen het woord REJECT."
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        # Korte pauze tegen rate limiting
        time.sleep(1.5)
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        
        # Diepe check van de JSON structuur
        if 'candidates' in data and len(data['candidates']) > 0:
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            return text
        return "Samenvatting niet gelukt."
    except Exception as e:
        print(f"Fout voor {title}: {e}")
        return "AI offline."

def run_scraper():
    print("--- START MEDIA SCRAPER ---")
    results = []
    # Kritische keywords voor tv-focus
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'borsato', 'vandaag inside', 'jinek', 'beau']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # Pak items met Regex
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = re.sub('<[^<]+?>', '', t_match.group(1).strip())
                    link = l_match.group(1).strip()

                    # Check op keywords
                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        # Alleen unieke linkjes
                        if not any(link in r for r in results):
                            summary = get_gemini_summary(title, name)
                            
                            # Filter irrelevante zaken (zoals dennenbossen/Soedan)
                            if "REJECT" in summary.upper() and len(summary) < 20:
                                continue

                            archive_link = f"https://archive.is/{link}"
                            results.append(f"""
                            <li style='margin-bottom: 20px; list-style: none;'>
                                <strong style='font-size: 16px; color: #333;'>[{name}] {title}</strong><br>
                                <p style='margin: 5px 0; color: #666; font-style: italic;'>{summary}</p>
                                <a href='{archive_link}' style='color: #007bff; text-decoration: none;'>🔓 Lees artikel via Archive.is</a>
                            </li>
                            """)
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    if not content:
        content = "<li>Geen media-artikelen gevonden vandaag.</li>"

    # Verzend de mail
    mail_url = "https://api.resend.com/emails"
    mail_payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"""
        <html>
            <body style='font-family: Arial, sans-serif; line-height: 1.6; max-width: 600px;'>
                <h2 style='color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 Media & TV Update</h2>
                <ul style='padding: 0;'>
                    {content}
                </ul>
            </body>
        </html>
        """
    }
    
    mail_headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(mail_url, headers=mail_headers, json=mail_payload, timeout=15)
        if response.status_code in [200, 201]:
            print("✅ Mail succesvol verzonden!")
        else:
            print(f"❌ Mail fout: {response.text}")
    except Exception as e:
        print(f"❌ Systeemfout: {e}")
