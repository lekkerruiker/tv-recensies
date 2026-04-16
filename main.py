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
        "Sorteer deze lijst voor een TV-professional. "
        "PRIORITEIT 1: TV-recensies (Volkskrant) en 'Zap' of 'Kijkt' (NRC). "
        "PRIORITEIT 2: Nieuws over NPO, RTL, SBS, talkshows, VI en presentatoren. "
        "Verwijder items die over buitenlandse politiek of religie gaan (Gaza, Soedan, kerk). "
        "Geef ENKEL de JSON lijst met ID-nummers terug."
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
    
    # VIP Recensenten
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong']
    
    # Specifieke TV termen (zonder losse 'kijkt' om ruis te voorkomen)
    TV_KEYWORDS = ['zap', 'nrc kijkt', 'tv-recensie', 'televisie', 'tv-', 'talkshow', 'vandaag inside', 'mafs', 'npo', 'rtl', 'sbs', 'presentator']
    
    # Omroepen
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

                    # --- DE VERFIJNDE FILTER ---
                    keep = False
                    
                    # 1. Volkskrant TV Sectie (De 'Holy Grail' voor de VK recensie)
                    if name == "Volkskrant" and "/televisie" in link.lower():
                        keep = True
                    
                    # 2. VIP Auteurs of NRC Zap
                    elif any(critic in title.lower() for critic in CRITICS) or 'zap' in title.lower():
                        keep = True

                    # 3. Harde TV keywords in de titel
                    elif any(word in title.lower() for word in TV_KEYWORDS):
                        keep = True
                    
                    # 4. Omroep context check
                    elif any(o in full_lower for o in OMROEPEN):
                        if any(x in full_lower for x in ['tv', 'televisie', 'uitzending', 'scherm']):
                            keep = True

                    # --- HARD BLOCK VOOR RUIS (Gaza/Soedan/Politiek) ---
                    if any(bad in title.lower() for bad in ['gaza', 'soedan', 'pkn', 'oekraïne']):
                        keep = False

                    if keep:
                        all_found.append({"title": title, "link": link, "source": name, "snippet": snippet})
                        seen_links.add(link)
        except: continue
    
    sorted_articles = get_ai_sorted_list(all_found)
    
    results_html = ""
    for i, art in enumerate(sorted_articles, 1):
        archive_link = f"https://archive.is/{art['link']}"
        border = "#e67e22" if i <= 5 else "#bdc3c7"
        results_html += f"""
        <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid {border}; padding-left: 15px;'>
            <strong style='font-size: 15px; color: #2c3e50;'>[{art['source']}] {art['title']}</strong><br>
            <p style='margin: 4px 0; color: #555; font-size: 13px;'>{art['snippet'][:160]}...</p>
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
            "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}",
            "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'><h2>📺 TV & Media Overzicht</h2><ul style='padding:0;'>{content}</ul></body></html>"
        }
    )
