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
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    text = " ".join(text.split())
    words = text.split()
    return " ".join(words[:25]) + "..." if len(words) > 25 else text

def run_scraper():
    print("🚀 Scraper start (Optimistische Sortering)...")
    results = []
    seen_links = set()
    
    # 1. Positieve Auteurs/Recensenten
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong', 'gaasbeek']
    
    # 2. Positieve TV/Media Termen
    TV_TERMS = [
        'zap', 'kijkt', 'recensie', 'televisie', 'tv-', 'talkshow', 'vandaag inside', 
        'mafs', 'npo', 'rtl', 'sbs', 'viaplay', 'netflix', 'videoland', 'hbomax', 
        'disney+', 'presentator', 'uitzending', 'kijkcijfers', 'omroep', 'serie', 
        'documentaire', 'film', 'programma', 'avrotros', 'powned', 'bnnvara', 
        'kro-ncrv', 'omroep max', 'wnl', 'vpro', 'human', 'ntr', 'omroep zwart', 'eo'
    ]

    # 3. Positieve URL-paden (voor secties die bijna altijd media zijn)
    MEDIA_PATHS = ['/televisie', '/media', '/cultuur-media', '/show', '/entertainment']

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

                    # Haal snippet op uit verschillende bronnen
                    desc_content = ""
                    for tag in ['description', 'content:encoded', 'summary']:
                        d_match = re.search(f'<{tag}>(.*?)</{tag}>', item, re.DOTALL)
                        if d_match:
                            desc_content = d_match.group(1)
                            break
                    snippet = clean_text(desc_content)
                    full_lower = (title + " " + snippet).lower()

                    # --- POSITIEVE FILTER LOGICA ---
                    keep = False
                    
                    # Check 1: Staat het in een media-sectie (URL)?
                    if any(path in link.lower() for path in MEDIA_PATHS):
                        keep = True
                    
                    # Check 2: Is het een bekende recensent?
                    if any(critic in title.lower() for critic in CRITICS):
                        keep = True
                    
                    # Check 3: Bevat het een van de positieve termen?
                    if any(term in full_lower for term in TV_TERMS):
                        keep = True

                    if keep:
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 22px; list-style: none; border-left: 4px solid #3498db; padding-left: 12px;'>
                            <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 6px 0; color: #444; font-size: 14px;'>{snippet if snippet else "<i>Geen intro beschikbaar in feed.</i>"}</p>
                            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 13px; font-weight: bold;'>🔓 Lees artikel</a>
                        </li>""")
                        seen_links.add(link)
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"TV & Media Update: {datetime.now().strftime('%d-%m')}",
            "html": f"""
            <html>
                <body style='font-family:sans-serif;max-width:650px;margin:0 auto;padding:20px;'>
                    <h2 style='color:#2980b9; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV & Media Selectie</h2>
                    <ul style='padding:0;'>{content if content else '<li>Geen media-artikelen gevonden op dit moment.</li>'}</ul>
                </body>
            </html>
            """
        }
    )
