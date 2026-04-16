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

def clean_text(raw_html):
    """Schoont HTML op en pakt de eerste 25 woorden."""
    if not raw_html:
        return "Geen beschrijving beschikbaar."
    # Verwijder HTML tags
    clean = re.sub(r'<[^>]+?>', '', raw_html)
    # Verwijder overtollige witruimte
    clean = " ".join(clean.split())
    # Pak de eerste 25 woorden
    words = clean.split()
    if len(words) > 25:
        return " ".join(words[:25]) + "..."
    return clean

def run_scraper():
    print("🚀 Scraper start (zonder AI)...")
    results = []
    seen_links = set()
    
    # De vertrouwde keywords
    KEYWORDS = ['lips', 'zap', 'peereboom', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'media', 'nijkamp', 'radio', 'talkshow', 'sonja', 'barend', 'borsato', 'vandaag inside', 'jinek', 'renze', 'beau', 'journalist', 'film', 'netflix', 'videoland']
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            # We splitsen de feed op items
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                d_match = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = re.sub('<[^<]+?>', '', t_match.group(1).strip())
                    link = l_match.group(1).strip()
                    description = d_match.group(1).strip() if d_match else ""

                    if link in seen_links: continue

                    # Check of het over media gaat via keywords
                    if any(k in (title + " " + description).lower() for k in KEYWORDS):
                        snippet = clean_text(description)
                        archive_link = f"https://archive.is/{link}"
                        
                        results.append(f"""
                        <li style='margin-bottom: 25px; list-style: none; border-left: 3px solid #3498db; padding-left: 10px;'>
                            <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 8px 0; color: #555; font-size: 14px; line-height: 1.4;'>{snippet}</p>
                            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-weight: bold;'>🔓 Lees artikel via Archive.is</a>
                        </li>""")
                        seen_links.add(link)
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    if not content:
        content = "<p>Geen media-artikelen gevonden vandaag.</p>"

    # Mail verzenden via Resend
    mail_payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"""
        <html>
            <body style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;'>
                <h2 style='color: #2c3e50;'>📺 Dagelijks Media Overzicht</h2>
                <p style='color: #999; font-size: 12px;'>De eerste 25 woorden van elk artikel:</p>
                <hr style='border: 0; border-top: 1px solid #eee;'>
                <ul style='padding: 0;'>{content}</ul>
            </body>
        </html>
        """
    }
    
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=mail_payload,
            timeout=20
        )
        print(f"✅ Mail verzonden: {r.status_code}")
    except Exception as e:
        print(f"❌ Fout: {e}")
