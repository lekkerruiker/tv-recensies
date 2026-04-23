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

# We gebruiken de meest stabiele RSS-feeds
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

def clean_text(text):
    if not text: return ""
    # Verwijder CDATA, HTML tags en overtollige witruimte
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def get_ai_decision(articles):
    """Laat de AI bepalen wat Prio 1, 2 of 3 is, of verwijderd moet worden."""
    if not articles:
        return {"prio1": [], "prio2": [], "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    input_data = [{"id": i, "title": a['title'], "source": a['source'], "link": a['link']} for i, a in enumerate(articles)]
    
    prompt = (
        "Je bent een media-expert die een dagelijkse nieuwsbrief samenstelt. Sorteer deze artikelen:\n\n"
        "Groep 1 (ORANJE - Prio 1): Dagelijkse TV-recensies (zoals Han Lips, Maaike Bos, de Zap-column van NRC, of TV-recensies van de Volkskrant).\n"
        "Groep 2 (BLAUW - Prio 2): Hard nieuws over de media-industrie, kijkcijfers, NPO/RTL updates en presentatoren.\n"
        "Groep 3 (GRIJS - Prio 3): Media-podcasts en lange interviews met TV-makers.\n\n"
        "VERWIJDER STRENG: Alles wat NIET met TV, Radio of Streaming te maken heeft. Geen algemene cultuur, boeken, kunst of politiek.\n"
        f"Lijst: {json.dumps(input_data)}\n\n"
        "Geef ENKEL een JSON terug in dit formaat: {\"prio1\": [ids], \"prio2\": [ids], \"prio3\": [ids]}"
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
    except Exception as e:
        print(f"AI error: {e}")
        # Fallback: alles in prio 2 als de AI faalt
        return {"prio1": [], "prio2": articles, "prio3": []}

def run_scraper():
    all_potential = []
    seen_links = set()
    
    # We vangen ALLES uit de RSS feeds van de laatste 24-48 uur
    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                if not l_match: continue
                link = l_match.group(1).strip()
                if link in seen_links: continue
                
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                title = clean_text(t_match.group(1)) if t_match else ""

                # We sturen een ruime selectie naar de AI (alles wat media-gerelateerd LIJKT)
                # We kijken naar woorden in de titel OF de URL
                media_triggers = ['tv', 'televisie', 'radio', 'kijkcijfers', 'podcast', 'streaming', 'netflix', 'zap', 'lips', 'bos', 'recensie', 'beeldbuis']
                if any(word in (title.lower() + link.lower()) for word in media_triggers):
                    all_potential.append({"title": title, "link": link, "source": name})
                    seen_links.add(link)
        except Exception as e:
            print(f"Feed error {name}: {e}")
            
    return get_ai_decision(all_potential)

def build_html_section(title, articles, color):
    if not articles: return ""
    html = f"<h3 style='color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px; margin-top: 30px;'>{title}</h3>"
    for art in articles:
        # Gebruik archive.is om betaalmuren te omzeilen
        html += f"<p style='margin-bottom: 12px;'><strong style='font-size: 15px;'>[{art['source']}] {art['title']}</strong><br><a href='https://archive.is/{art['link']}' style='color: #3498db; text-decoration: none; font-size: 13px;'>🔓 Lees artikel</a></p>"
    return html

if __name__ == "__main__":
    prio_data = run_scraper()
    
    content = build_html_section("⭐ De Dagelijkse Recensies", prio_data['prio1'], "#e67e22")
    content += build_html_section("📺 Media Nieuws", prio_data['prio2'], "#2980b9")
    content += build_html_section("🎧 Podcasts & Verdieping", prio_data['prio3'], "#7f8c8d")
    
    if any(prio_data.values()):
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'>{content}</body></html>"
            })
