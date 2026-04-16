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
    print("🚀 Scraper start (Scherpschutter Modus)...")
    results = []
    seen_links = set()
    
    # 1. VIP-Lijst: Deze namen duiden bijna altijd op een TV-recensie
    VIP_CRITICS = ['lips:', 'fortuin:', 'peereboom:', 'maaike bos:', 'stokmans:', 'han lips']
    
    # 2. Harde TV-Keywords (moeten in titel of snippet staan)
    HARD_TV = [
        'tv-recensie', 'tv-column', 'kijkcijfers', 'vandaag inside', 'talkshow', 
        'presentator', 'uitzending', 'npo 1', 'npo 2', 'npo 3', 'rtl 4', 'sbs 6',
        'tina nijkamp', 'angela de jong', 'jinek', 'beau', 'renze', 'humberto'
    ]

    # 3. Zachte Keywords (mogen alleen door als ze gecombineerd worden met TV-context)
    SOFT_KEYWORDS = ['serie', 'omroep', 'netflix', 'videoland', 'documentaire', 'film']

    # 4. Verboden Woorden (Uitsluiten van ruis)
    FORBIDDEN = [
        'omroepkoor', 'museum', 'concert', 'klimaat', 'beurs', 'sport', 'voetbal', 
        'politiek', 'kamerlid', 'minister', 'oorlog', 'gaza', 'israël', 'oekraïne'
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

                    # Snippet ophalen
                    desc_content = ""
                    for tag in ['description', 'content:encoded', 'summary']:
                        d_match = re.search(f'<{tag}>(.*?)</{tag}>', item, re.DOTALL)
                        if d_match:
                            desc_content = d_match.group(1)
                            break
                    snippet = clean_text(desc_content)
                    full_lower = (title + " " + snippet).lower()

                    # --- FILTER LOGICA ---
                    keep = False
                    
                    # A. Check VIP Critics (Hoge prioriteit)
                    if any(critic in title.lower() for critic in VIP_CRITICS):
                        keep = True
                    
                    # B. Check Harde TV Keywords
                    if any(word in full_lower for word in HARD_TV):
                        keep = True
                        
                    # C. Check Zachte Keywords (alleen als titel ook 'televisie' of 'kijkt' bevat)
                    if any(soft in full_lower for soft in SOFT_KEYWORDS):
                        if any(tv in full_lower for tv in ['tv', 'televisie', 'kijkt', 'scherm', 'streamen']):
                            keep = True

                    # D. Harde Uitsluiting (Zelfs als een keyword matcht, gooi weg bij ruis)
                    if any(forbidden in full_lower for forbidden in FORBIDDEN):
                        # Uitzondering: als het over een talkshow gaat, mag het wel
                        if not any(ts in full_lower for ts in ['talkshow', 'vandaag inside', 'op1']):
                            keep = False

                    if keep:
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 20px; list-style: none; border-left: 4px solid #e67e22; padding-left: 12px;'>
                            <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 4px 0; color: #444; font-size: 14px;'>{snippet if snippet else "<i>Geen intro.</i>"}</p>
                            <a href='{archive_link}' style='color: #e67e22; text-decoration: none; font-size: 13px; font-weight: bold;'>🔓 Lees artikel</a>
                        </li>""")
                        seen_links.add(link)
        except:
            continue
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    if not content:
        content = "<li>Geen specifieke TV-recensies of media-items gevonden vandaag.</li>"

    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"TV Focus: {datetime.now().strftime('%d-%m')}",
            "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;'><h2>📺 TV & Media Focus</h2><ul>{content}</ul></body></html>"
        }
    )
