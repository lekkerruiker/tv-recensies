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
    
    # We geven de AI nu de opdracht om BREDE media-interesses te accepteren
    prompt = (
        f"Je bent een media-expert. Analyseer deze titel: '{title}' (Bron: {source}).\n"
        "VRAAG: Gaat dit over televisie, streaming (Netflix/Videoland), radio, BN'ers, journalistiek, "
        "podcasts of de invloed van media? \n"
        "- Als het JA is (of zelfs een beetje gerelateerd): Schrijf 1 vlotte samenvatting van max 15 woorden in het Nederlands.\n"
        "- Als het ECHT NIET over media gaat (zoals natuur, buitenlands beleid, sport zonder media-link): Antwoord met alleen het woord REJECT."
    )
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        time.sleep(1) # Voorkom rate limit
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data and data['candidates']:
                text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                # Debugging: we printen de beslissing in de GitHub logs
                print(f"AI Check: '{title[:30]}...' -> {text[:20]}")
                return text
        return "REJECT"
    except:
        return "REJECT"

def run_scraper():
    print("🚀 Scraper start...")
    results = []
    
    # We breiden de keywords uit zodat er meer naar de AI wordt gestuurd
    KEYWORDS = [
        'lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 
        'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'barend', 'borsato', 
        'vandaag inside', 'jinek', 'renze', 'beau', 'journalist', 'cultuur', 
        'film', 'programma', 'presentator', 'uitzending', 'nieuwsbericht'
    ]
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

                    # Check trefwoorden (stap 1)
                    if any(k in (title + " " + link).lower() for k in KEYWORDS):
                        # Laat AI beslissen (stap 2)
                        summary = get_gemini_summary(title, name)
                        
                        if "REJECT" not in summary.upper():
                            archive_link = f"https://archive.is/{link}"
                            results.append(f"""
                            <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid #e67e22; padding-left: 15px;'>
                                <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                                <p style='margin: 8px 0; color: #444; font-size: 14px;'>{summary}</p>
                                <a href='{archive_link}' style='color: #e67e22; text-decoration: none; font-weight: bold;'>🔓 Lees artikel</a>
                            </li>""")
        except Exception as e:
            print(f"⚠️ Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    articles_html = run_scraper()
    
    # Onderwerp en inhoud bepalen
    if not articles_html:
        subject = f"Media Update [GEEN NIEUWS]: {datetime.now().strftime('%d-%m')}"
        body_content = "<p>Vandaag geen specifieke media-artikelen gevonden in de geselecteerde feeds.</p>"
    else:
        subject = f"Media Update: {datetime.now().strftime('%d-%m')}"
        body_content = f"<ul style='padding: 0;'>{articles_html}</ul>"

    # Verzend mail via Resend
    mail_url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": subject,
        "html": f"""
        <html>
            <body style='font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif; max-width: 600px; padding: 20px;'>
                <h2 style='color: #e67e22;'>📺 Media & TV Update</h2>
                <hr style='border: 1px solid #eee;'>
                {body_content}
            </body>
        </html>
        """
    }
    
    r = requests.post(mail_url, headers=headers, json=payload, timeout=20)
    print(f"✅ Klaar. Mail status: {r.status_code}")
