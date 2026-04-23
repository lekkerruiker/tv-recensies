import os
import requests
import re
from datetime import datetime, timedelta
import json

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Alleen artikelen met deze woorden (of in deze secties) komen in de voorselectie
STRICT_MEDIA_WORDS = [
    'tv', 'televisie', 'radio', 'kijkcijfers', 'podcast', 'streaming', 'netflix', 
    'videoland', 'npo', 'rtl', 'sbs', 'vi', 'vandaag inside', 'jinek', 'lubach', 
    'humberto', 'beau', 'renze', 'even tot hier', 'recensie', 'beeldbuis', 'omroep'
]

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def get_ai_decision(articles):
    if not articles:
        return {"prio1": [], "prio2": [], "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(articles)]
    
    prompt = (
        "Je bent een filter voor een media-expert. Sorteer de lijst in drie categorieën:\n"
        "1. 'prio1': Echte TV-recensies of dagelijkse media-columns (zoals over een specifiek tv-programma).\n"
        "2. 'prio2': Hard nieuws over zenders, kijkcijfers, presentatoren of streaming-diensten.\n"
        "3. 'prio3': Media-podcasts en interviews met tv-makers.\n\n"
        "BELANGRIJK: Verwijder alles wat gaat over: boeken, theater, musea, popmuziek, politiek of algemene maatschappij. "
        "Als het niet DIRECT over TV, Radio of de media-industrie gaat, gooi het dan weg.\n"
        f"Lijst: {json.dumps(input_data)}\n"
        "Antwoord enkel met JSON: {\"prio1\": [ids], \"prio2\": [ids], \"prio3\": [ids]}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
        raw_response = resp.json()['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(re.search(r'\{.*\}', raw_response, re.DOTALL).group())
        
        return {
            "prio1": [articles[i] for i in data.get("prio1", []) if i < len(articles)],
            "prio2": [articles[i] for i in data.get("prio2", []) if i < len(articles)],
            "prio3": [articles[i] for i in data.get("prio3", []) if i < len(articles)]
        }
    except:
        return {"prio1": [], "prio2": [], "prio3": []}

def run_scraper():
    all_potential = []
    seen_links = set()
    
    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                if not l_match: continue
                link = l_match.group(1).strip()
                if link in seen_links: continue
                
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                title = clean_text(t_match.group(1)) if t_match else ""
                
                title_lower = title.lower()
                link_lower = link.lower()

                # VIP CHECK: Deze moeten ALTIJD door naar de AI (of direct naar Prio 1)
                is_vip = any(x in link_lower for x in ['/televisie', '/zap', 'han-lips', 'maaike-bos'])
                
                # MEDIA CHECK: Bevat de titel media-trefwoorden?
                has_keyword = any(kw in title_lower for kw in STRICT_MEDIA_WORDS)

                if is_vip or has_keyword:
                    all_potential.append({"title": title, "link": link, "source": name})
                    seen_links.add(link)
        except: continue
            
    return get_ai_decision(all_potential)

def build_html_section(title, articles, color):
    if not articles: return ""
    html = f"<div style='margin-bottom: 25px;'><h3 style='color: {color}; border-bottom: 1px solid {color}; margin-bottom: 10px;'>{title}</h3>"
    for art in articles:
        html += f"<div style='margin-bottom: 8px;'><strong>[{art['source']}]</strong> {art['title']} <a href='https://archive.is/{art['link']}' style='font-size: 12px; color: #3498db; text-decoration: none;'>[Lees]</a></div>"
    return html + "</div>"

if __name__ == "__main__":
    prio_data = run_scraper()
    
    content = build_html_section("⭐ De Dagelijkse Recensies", prio_data['prio1'], "#e67e22")
    content += build_html_section("📺 Media Nieuws", prio_data['prio2'], "#2980b9")
    content += build_html_section("🎧 Podcasts & Verdieping", prio_data['prio3'], "#7f8c8d")
    
    if content:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family: Arial, sans-serif; line-height: 1.5; color: #333;'>{content}</body></html>"
            })
