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

# We focussen nu 100% op de RSS-feeds omdat de directe sites ons blokkeren
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
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def get_ai_prioritized_articles(articles):
    # Splits de lijst in "VIP" (Prio 1) en de rest voor de AI
    prio1_list = [a for a in articles if a['prio_override']]
    others = [a for a in articles if not a['prio_override']]

    if not others:
        return {"prio1": prio1_list, "prio2": [], "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(others)]
    
    prompt = (
        "Je bent een media-expert. Filter deze nieuwslijst.\n"
        "Groep 2: Hard nieuws over TV-programma's, kijkcijfers, presentatoren en zenders.\n"
        "Groep 3: Media-podcasts en diepgaande interviews met TV-makers.\n"
        "VERWIJDER STRENG: Alles wat niet met TV/Radio/Streaming te maken heeft. Geen algemene cultuur, geen boeken, geen politiek.\n"
        f"Lijst: {json.dumps(input_data)}\n"
        "Antwoord enkel met JSON: {\"prio2\": [ids], \"prio3\": [ids]}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        res_json = resp.json()
        raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group())
        return {
            "prio1": prio1_list,
            "prio2": [others[i] for i in data.get("prio2", []) if i < len(others)],
            "prio3": [others[i] for i in data.get("prio3", []) if i < len(others)]
        }
    except:
        return {"prio1": prio1_list, "prio2": [], "prio3": []}

def run_scraper():
    all_found, seen_links = [], set()
    
    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            # We knippen de RSS handmatig op om CDATA en vreemde tekens beter te vangen
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                if not l_match: continue
                link = l_match.group(1).strip()
                if link in seen_links: continue
                
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                title = clean_text(t_match.group(1)) if t_match else ""
                
                full_lower = (title + " " + link).lower()
                is_prio = False
                source_label = name

                # VIP LOGICA (Wat moet ALTIJD in oranje?)
                # 1. Volkskrant TV
                if "volkskrant.nl" in link and "/televisie" in link:
                    source_label, is_prio = "Volkskrant TV", True
                # 2. NRC Zap
                elif "nrc.nl" in link and "/zap" in link:
                    source_label, is_prio = "NRC Zap", True
                # 3. Han Lips
                elif "han-lips" in link or "han lips" in title.lower():
                    source_label, is_prio = "Parool: Han Lips", True
                # 4. Maaike Bos
                elif "maaike-bos" in link or "maaike bos" in title.lower():
                    source_label, is_prio = "Trouw: Maaike Bos", True
                
                # Check of het überhaupt media-relevant is (voor de rest)
                media_keywords = ['tv', 'televisie', 'radio', 'kijkcijfers', 'podcast', 'presentator', 'streaming', 'netflix', 'videoland']
                is_media = any(kw in full_lower for kw in media_keywords)

                if is_prio or is_media:
                    all_found.append({
                        "title": title, 
                        "link": link, 
                        "source": source_label, 
                        "prio_override": is_prio
                    })
                    seen_links.add(link)
        except: continue
            
    return get_ai_prioritized_articles(all_found)

def build_html_section(title, articles, color):
    if not articles: return ""
    html = f"<h3 style='color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px; margin-top: 30px;'>{title}</h3>"
    for art in articles:
        html += f"<p style='margin-bottom: 12px;'><strong style='font-size: 15px;'>[{art['source']}] {art['title']}</strong><br><a href='https://archive.is/{art['link']}' style='color: #3498db; text-decoration: none; font-size: 13px;'>🔓 Lees artikel</a></p>"
    return html

if __name__ == "__main__":
    prio_data = run_scraper()
    
    content = build_html_section("⭐ Belangrijkste Recensies", prio_data['prio1'], "#e67e22")
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
