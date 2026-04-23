import os
import requests
import re
from datetime import datetime, timedelta
import json
from bs4 import BeautifulSoup

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Brede media-focus voor RSS filtering
MEDIA_KEYWORDS = [
    'tv', 'televisie', 'recensie', 'talkshow', 'npo', 'rtl', 'sbs', 'vi', 
    'vandaag inside', 'kijkcijfers', 'omroep', 'presentator', 'streaming', 
    'netflix', 'videoland', 'radio', 'podcast', 'beau', 'humberto', 'renze', 
    'jinek', 'lubach', 'even tot hier'
]

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def scrape_direct_pages():
    articles = []
    today_str = datetime.now().strftime("/%Y/%m/%d/")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("/%Y/%m/%d/")
    
    # 1. VOLKSKRANT TV SECTIE (Directe extractie van de pagina)
    try:
        vk_url = "https://www.volkskrant.nl/televisie/"
        resp = requests.get(vk_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            count = 0
            # We pakken de artikelen die in de 'televisie' sectie staan
            for a in soup.find_all('a', href=True):
                link = a['href']
                title = a.get_text().strip()
                
                # Check of het een artikel-link is in de juiste sectie
                if "/televisie/" in link and len(title) > 25:
                    full_link = f"https://www.volkskrant.nl{link}" if not link.startswith('http') else link
                    articles.append({
                        "title": title, 
                        "link": full_link, 
                        "source": "Volkskrant TV-Recensie"
                    })
                    count += 1
                if count >= 4: break # De bovenste artikelen zijn meestal de recensies
    except Exception as e:
        print(f"Fout bij VK scrape: {e}")

    # 2. NRC ZAP
    try:
        nrc_url = "https://www.nrc.nl/onderwerp/zap/"
        resp = requests.get(nrc_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            count = 0
            for a in soup.find_all('a', href=True):
                link = a['href']
                title = a.get_text().strip()
                if (today_str in link or yesterday_str in link) and len(title) > 15:
                    full_link = f"https://www.nrc.nl{link}" if not link.startswith('http') else link
                    articles.append({"title": title, "link": full_link, "source": "NRC Zap"})
                    count += 1
                if count >= 2: break
    except: pass

    return articles

def get_ai_prioritized_articles(articles):
    # Alles met deze labels gaat direct naar Prio 1 (Oranje)
    prio1_labels = ["Volkskrant TV-Recensie", "NRC Zap", "Parool: Han Lips", "Trouw: Maaike Bos"]
    prio1_list = [a for a in articles if a['source'] in prio1_labels]
    
    # De rest (RSS vandaan) wordt gefilterd door de AI
    others = [a for a in articles if a['source'] not in prio1_labels]

    if not others:
        return {"prio1": prio1_list, "prio2": [], "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(others)]
    
    prompt = (
        "Je bent een media-expert. Filter de volgende lijst met nieuws-titels.\n"
        "Groep 2: Belangrijk nieuws over TV, Radio en Streaming (kijkcijfers, nieuwe programma's, presentatoren).\n"
        "Groep 3: Media-gerelateerde podcasts en diepte-interviews.\n"
        "VERWIJDER STRENG: Alles wat NIET over media gaat (geen algemene cultuur, boeken, natuur of politiek).\n"
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
    except Exception as e:
        print(f"AI Filter fout: {e}")
        return {"prio1": prio1_list, "prio2": [], "prio3": []}

def run_scraper():
    all_found, seen_links = [], set()
    
    # 1. Prio 1 vangers (Direct van de pagina's)
    for art in scrape_direct_pages():
        if art['link'] not in seen_links:
            all_found.append(art); seen_links.add(art['link'])

    # 2. RSS Vangnet
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
                
                # Snelle pre-filter op trefwoorden om ruis voor de AI te beperken
                if any(kw in title.lower() for kw in MEDIA_KEYWORDS) or any(kw in link.lower() for kw in ['televisie', 'media', 'podcast']):
                    source = name
                    # Specifieke columns herkennen in RSS
                    if "han-lips" in link: source = "Parool: Han Lips"
                    elif "maaike-bos" in link: source = "Trouw: Maaike Bos"
                    elif "volkskrant.nl/televisie" in link: source = "Volkskrant TV-Recensie"
                    
                    all_found.append({"title": title, "link": link, "source": source})
                    seen_links.add(link)
        except: continue
            
    return get_ai_prioritized_articles(all_found)

def build_html_section(title, articles, color):
    if not articles: return ""
    html = f"<h3 style='color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px; margin-top: 30px;'>{title}</h3>"
    for art in articles:
        # Gebruik archive.is om betaalmuren te omzeilen
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
