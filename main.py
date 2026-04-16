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
    print("🚀 Scraper start (Recensie-Prioriteit)...")
    results = []
    seen_links = set()
    
    # VIP: Als een van deze namen in de TITEL staat, is het bijna altijd een recensie.
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong']
    
    # TV Keywords (moeten gecombineerd worden met TV context)
    TV_CORE = ['zap', 'kijkt', 'recensie', 'televisie', 'tv-', 'talkshow', 'vandaag inside', 'presentator', 'uitzending', 'npo', 'rtl', 'sbs']

    FORBIDDEN = ['omroepkoor', 'klimaat', 'beurs', 'voetbaluitslagen', 'oorlog', 'gaza']

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

                    # Haal tekst op
                    desc_content = ""
                    for tag in ['description', 'content:encoded', 'summary']:
                        d_match = re.search(f'<{tag}>(.*?)</{tag}>', item, re.DOTALL)
                        if d_match:
                            desc_content = d_match.group(1)
                            break
                    snippet = clean_text(desc_content)
                    full_lower = (title + " " + snippet).lower()

                    # --- DE NIEUWE FILTER LOGICA ---
                    keep = False
                    
                    # 1. Is het een bekende recensent? (Hoge prioriteit)
                    if any(critic in title.lower() for critic in CRITICS):
                        keep = True
                    
                    # 2. Bevat het een 'Harde' TV term in de titel?
                    if any(word in title.lower() for word in ['zap', 'recensie', 'tv-column', 'kijkt']):
                        keep = True

                    # 3. Bevat de tekst TV-context?
                    if any(word in full_lower for word in TV_CORE):
                        # Alleen als het niet over verboden onderwerpen gaat
                        if not any(f in full_lower for f in FORBIDDEN):
                            keep = True

                    # Extra check: Forceer uitsluiting bij ruis, behalve voor VIP recensenten
                    if any(f in full_lower for f in FORBIDDEN):
                        if not any(critic in title.lower() for critic in CRITICS):
                            keep = False

                    if keep:
                        archive_link = f"https://archive.is/{link}"
                        results.append(f"""
                        <li style='margin-bottom: 22px; list-style: none; border-left: 4px solid #3498db; padding-left: 12px;'>
                            <strong style='font-size: 16px; color: #2c3e50;'>[{name}] {title}</strong><br>
                            <p style='margin: 6px 0; color: #444; font-size: 14px;'>{snippet if snippet else "<i>Geen intro.</i>"}</p>
                            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 13px; font-weight: bold;'>🔓 Lees recensie</a>
                        </li>""")
                        seen_links.add(link)
        except:
            continue
            
    return "".join(results)

if __name__ == "__main__":
    content = run_scraper()
    
    # Altijd mailen
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"TV Recensies & Media: {datetime.now().strftime('%d-%m')}",
            "html": f"""
            <html>
                <body style='font-family:sans-serif;max-width:650px;margin:0 auto;padding:20px;'>
                    <h2 style='color: #2980b9; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 Dagelijkse TV Selectie</h2>
                    <ul style='padding: 0;'>{content if content else "<li>Vandaag geen recensies gevonden.</li>"}</ul>
                </body>
            </html>
            """
        }
    )
