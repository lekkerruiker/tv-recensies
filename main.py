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
    print("🚀 Scraper start (Focus op het Scherm)...")
    results = []
    seen_links = set()
    
    # 1. VIP Recensenten (ALTIJD raak)
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong']
    
    # 2. Harde TV-Termen (Directe match)
    HARD_TV = [
        'zap', 'kijkt', 'tv-recensie', 'televisie', 'tv-', 'talkshow', 'vandaag inside', 
        'mafs', 'npo', 'rtl', 'sbs', 'kijkcijfers', 'presentator', 'uitzending', 'omroep'
    ]

    # 3. Omroepen (Directe match)
    OMROEPEN = ['avrotros', 'powned', 'bnnvara', 'kro-ncrv', 'omroep max', 'wnl', 'vpro', 'human', 'ntr', 'omroep zwart', 'eo']

    # 4. Streaming (Alleen als het specifiek over de dienst/serie gaat)
    STREAMING = ['netflix', 'videoland', 'hbomax', 'disney+', 'viaplay', 'prime video', 'npo start']

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

                    desc_content = ""
                    for tag in ['description', 'content:encoded', 'summary']:
                        d_match = re.search(f'<{tag}>(.*?)</{tag}>', item, re.DOTALL)
                        if d_match:
                            desc_content = d_match.group(1)
                            break
                    snippet = clean_text(desc_content)
                    full_lower = (title + " " + snippet).lower()

                    # --- DE NIEUWE FOCUS-FILTER ---
                    keep = False
                    
                    # A. Check URL Sectie (Strenge selectie)
                    if any(path in link.lower() for path in ['/televisie', '/media']):
                        keep = True
                    
                    # B. Check bekende recensenten
                    if any(critic in title.lower() for critic in CRITICS):
                        keep = True
                    
                    # C. Check Harde TV termen
                    if any(term in full_lower for term in HARD_TV):
                        keep = True
                    
                    # D. Check Omroepen
                    if any(omroep in full_lower for omroep in OMROEPEN):
                        keep = True
                    
                    # E. Check Streaming (alleen als titel ook 'serie' of 'kijkt' bevat)
                    if any(s in full_lower for s in STREAMING):
                        if any(x in full_lower for x in ['serie', 'kijkt', 'seizoen', 'aflevering']):
                            keep = True

                    # EXTRA: Gooi algemene film- en kunstberichten eruit die per ongeluk 'omroep' of 'kijkt' bevatten
                    if 'film' in full_lower and not any(x in full_lower for x in ['tv', 'televisie', 'npo', 'rtl', 'sbs', 'stream']):
                        if not any(critic in title.lower() for critic in CRITICS):
                            keep = False

                    if keep:
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 22px; list-style: none; border-left: 3px solid #e67e22; padding-left: 12px;'>
                            <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 6px 0; color: #444; font-size: 14px;'>{snippet if snippet else "<i>Geen intro beschikbaar.</i>"}</p>
                            <a href='{archive_link}' style='color: #e67e22; text-decoration: none; font-size: 13px; font-weight: bold;'>🔓 Lees artikel</a>
                        </li>""")
                        seen_links.add(link)
        except:
            continue
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"TV Focus: {datetime.now().strftime('%d-%m')}",
            "html": f"<html><body style='font-family:sans-serif;max-width:650px;margin:0 auto;padding:20px;'><h2 style='color:#e67e22; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV & Media Focus</h2><ul style='padding:0;'>{content if content else '<li>Geen scherpe TV-matches gevonden.</li>'}</ul></body></html>"
        }
    )
