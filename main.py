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
    if not text: return ""
    # Verwijder CDATA, HTML en vreemde tekens
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    text = " ".join(text.split())
    words = text.split()
    return " ".join(words[:25]) + "..." if len(words) > 25 else text

def run_scraper():
    print("🚀 Scraper start (Recensies, TV & Omroepen)...")
    results = []
    seen_links = set()
    
    # 1. TV-recensenten
    TV_CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels']
    
    # 2. Uitgebreide TV & Omroep keywords
    TV_KEYWORDS = [
        'zap', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-', 'nijkamp', 
        'talkshow', 'vandaag inside', 'jinek', 'renze', 'beau', 'omroep', 
        'streaming', 'netflix', 'videoland', 'kijkcijfers', 'presentator',
        'avrotros', 'powned', 'bnnvara', 'kro-ncrv', 'omroep max', 'wnl', 
        'vpro', 'human', 'ntr', 'omroep zwart', 'eo', 'npo'
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = clean_text(t_match.group(1))
                    link = l_match.group(1).strip()
                    if link in seen_links: continue

                    # Zoek naar snippets in verschillende velden
                    desc_content = ""
                    for tag in ['description', 'content:encoded', 'summary']:
                        d_match = re.search(f'<{tag}>(.*?)</{tag}>', item, re.DOTALL)
                        if d_match:
                            desc_content = d_match.group(1)
                            break
                    
                    snippet = clean_text(desc_content)
                    full_text_to_check = (title + " " + snippet).lower()

                    # Filter logica
                    is_tv_content = False
                    
                    # Criterium A: Recensent in titel
                    if any(critic in title.lower() for critic in TV_CRITICS):
                        is_tv_content = True
                    
                    # Criterium B: Keywords of omroepen aanwezig
                    if any(k in full_text_to_check for k in TV_KEYWORDS):
                        is_tv_content = True

                    # Uitsluitingen (om ruis te voorkomen)
                    if any(x in title.lower() for x in ['sahel', 'soedan', 'beurs', 'voetbaluitslagen']):
                        is_tv_content = False

                    if is_tv_content:
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
        content = "<li>Geen nieuwe TV-recensies of omroepnieuws gevonden vandaag.</li>"

    mail_payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"TV & Media Update: {datetime.now().strftime('%d-%m')}",
        "html": f"""
        <html>
            <body style='font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; line-height: 1.5;'>
                <h2 style='color: #e67e22; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV & Media Overzicht</h2>
                <ul style='padding: 0;'>{content}</ul>
                <p style='color: #999; font-size: 11px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 10px;'>
                    Gefilterd op recensenten, omroepen (NPO/VPRO/MAX etc.) en TV-nieuws.
                </p>
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
        print(f"❌ Mail fout: {e}")
