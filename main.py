import os
import requests
import re
from datetime import datetime

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def clean_text(text):
    """Schoont tekst op, verwijdert HTML en CDATA rommel."""
    if not text:
        return ""
    # Verwijder CDATA en HTML tags
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    # Verwijder overtollige witruimte
    text = " ".join(text.split())
    # Pak de eerste 25 woorden
    words = text.split()
    if len(words) > 25:
        return " ".join(words[:25]) + "..."
    return text

def run_scraper():
    print("🚀 Scraper start (focus op TV/Media)...")
    results = []
    seen_links = set()
    
    # VEEL strengere selectie op TV/Media keywords
    STRICT_KEYWORDS = [
        'lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 
        'nijkamp', 'talkshow', 'vandaag inside', 'jinek', 'renze', 'beau', 'presentator', 
        'uitzending', 'programma', 'kijkcijfers', 'omroep', 'streaming', 'netflix', 'videoland'
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                # Titel en Link
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = clean_text(t_match.group(1))
                    link = l_match.group(1).strip()
                    
                    if link in seen_links: continue

                    # Probeer beschrijving te vinden in verschillende velden (sommige kranten wisselen dit af)
                    desc_match = re.search(r'<(?:description|content:encoded|summary)>(.*?)</(?:description|content:encoded|summary)>', item, re.DOTALL)
                    raw_desc = desc_match.group(1) if desc_match else ""
                    snippet = clean_text(raw_desc)

                    # FILTER: Moet een van de keywords bevatten
                    if any(k in (title + " " + snippet).lower() for k in STRICT_KEYWORDS):
                        # Extra check: sluit algemeen nieuws uit dat vaak per ongeluk 'media' bevat
                        if any(x in title.lower() for x in ['sahel', 'toerisme', 'gaza', 'soedan']):
                            continue

                        archive_link = f"https://archive.is/{link}"
                        
                        results.append(f"""
                        <li style='margin-bottom: 25px; list-style: none; border-left: 3px solid #e67e22; padding-left: 12px;'>
                            <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 6px 0; color: #444; font-size: 14px; line-height: 1.5;'>
                                {snippet if snippet else "<i>Geen intro beschikbaar in feed.</i>"}
                            </p>
                            <a href='{archive_link}' style='color: #e67e22; text-decoration: none; font-size: 13px; font-weight: bold;'>🔓 Lees artikel via Archive.is</a>
                        </li>""")
                        seen_links.add(link)
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    if not content:
        content = "<p style='color: #666;'>Geen specifieke TV-artikelen gevonden vandaag.</p>"

    mail_payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"TV & Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"""
        <html>
            <body style='font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;'>
                <h2 style='color: #e67e22; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV & Media Overzicht</h2>
                <ul style='padding: 0;'>{content}</ul>
                <p style='color: #999; font-size: 11px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 10px;'>
                    Gefilterd op TV-relevante trefwoorden.
                </p>
            </body>
        </html>
        """
    }
    
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=mail_payload,
        timeout=20
    )
