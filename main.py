import os
import requests
import re
from datetime import datetime
import json

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

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def get_ai_sorted_list(articles):
    if not GEMINI_KEY or not articles:
        return articles
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(articles)]
    
    prompt = (
        "Sorteer deze lijst met media-artikelen voor een TV-professional. "
        "PRIORITEIT 1: TV-recensies (Volkskrant) en 'Zap' (NRC). Dit zijn de belangrijkste dagelijkse stukken. "
        "PRIORITEIT 2: Nieuws over NPO, RTL, SBS, talkshows en presentatoren. "
        "Zet de belangrijkste items bovenaan en geef ENKEL de JSON lijst met ID-nummers terug in de nieuwe volgorde. "
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_response = resp.json()['candidates'][0]['content']['parts'][0]['text']
        ids = json.loads(re.search(r'\[.*\]', raw_response).group())
        return [articles[i] for i in ids if i < len(articles)]
    except:
        return articles

def run_scraper():
    all_found = []
    seen_links = set()
    
    # 1. VIP Auteurs (NRC & overig)
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'stokmans', 'wels', 'nijkamp', 'angela de jong']
    
    # 2. Harde TV-Keywords
    TV_KEYWORDS = ['zap', 'kijkt', 'tv-recensie', 'televisie', 'tv-', 'talkshow', 'vandaag inside', 'mafs', 'npo', 'rtl', 'sbs']
    
    # 3. Omroepen
    OMROEPEN = ['avrotros', 'powned', 'bnnvara', 'kro-ncrv', 'omroep max', 'wnl', 'vpro', 'human', 'ntr', 'omroep zwart', 'eo']

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

                    desc_match = re.search(r'<(?:description|content:encoded|summary)>(.*?)</(?:description|content:encoded|summary)>', item, re.DOTALL)
                    snippet = clean_text(desc_match.group(1)) if desc_match else ""
                    full_lower = (title + " " + snippet + " " + link).lower()

                    keep = False
                    
                    # --- DE VIP & STRENGE FILTER ---
                    
                    # VIP CHECK 1: De Volkskrant Recensie (Ongeacht auteur)
                    # We herkennen deze aan de URL-sectie '/televisie' of de term 'tv-recensie' bij de VK
                    if name == "Volkskrant" and ('/televisie' in link.lower() or 'tv-recensie' in full_lower):
                        keep = True
                    
                    # VIP CHECK 2: Bekende recensenten (NRC Lips/Fortuin etc)
                    elif any(critic in title.lower() for critic in CRITICS):
                        keep = True
                    
                    # VIP CHECK 3: NRC Zap (Altijd prio)
                    elif name == "NRC" and 'zap' in title.lower():
                        keep = True

                    # REGULIER FILTER: Alleen als het echt over TV gaat
                    elif any(word in full_lower for word in TV_KEYWORDS):
                        if any(o in full_lower for o in OMROEPEN) or any(tv in title.lower() for tv in ['tv', 'televisie', 'kijkt']):
                            keep = True

                    if keep:
                        all_found.append({
                            "title": title, "link": link, "source": name, "snippet": snippet
                        })
                        seen_links.add(link)
        except: continue
    
    # AI Sortering zorgt dat de VIPs (die we hierboven hebben gemarkeerd) bovenaan komen
    sorted_articles = get_ai_sorted_list(all_found)
    
    results_html = ""
    for i, art in enumerate(sorted_articles, 1):
        archive_link = f"https://archive.is/{art['link']}"
        # Visueel onderscheid voor de absolute top
        border = "#e67e22" if i <= 5 else "#bdc3c7"
        
        results_html += f"""
        <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid {border}; padding-left: 15px;'>
            <strong style='font-size: 15px; color: #2c3e50;'>[{art['source']}] {art['title']}</strong><br>
            <p style='margin: 4px 0; color: #555; font-size: 14px;'>{art['snippet'][:160]}...</p>
            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 12px; font-weight: bold;'>🔓 Lees artikel</a>
        </li>"""
    return results_html

if __name__ == "__main__":
    content = run_scraper()
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM, "to": [EMAIL_RECEIVER],
            "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
            "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'><h2>📺 TV & Media Overzicht</h2><ul style='padding:0;'>{content}</ul></body></html>"
        }
    )
