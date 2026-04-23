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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

MEDIA_KEYWORDS = [
    'tv', 'televisie', 'talkshow', 'npo', 'rtl', 'sbs', 'veronica', 'kijkcijfer', 
    'omroep', 'presentator', 'streaming', 'netflix', 'videoland', 'radio', 
    'podcast', '538', 'q-music', 'kink', '3fm', 'luistercijfer', 'humberto', 
    'beau', 'vandaag inside', 'renze', 'op1', 'eva jinek', 'arjen lubach', 'tv-recensie'
]

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def scrape_volkskrant_direct():
    """Specifieke diepe scan voor de Volkskrant TV-pagina"""
    articles = []
    url = "https://www.volkskrant.nl/televisie/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            # We zoeken met Regex direct in de HTML-broncode naar links
            # Dit werkt vaak beter bij moderne sites dan BeautifulSoup alleen
            links = re.findall(r'href="(/televisie/[^"]+?~b[^"]+?)"', resp.text)
            # Ook titels proberen te vangen die vaak in de buurt staan
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            seen_local = set()
            for link in links:
                if link in seen_local: continue
                full_link = f"https://www.volkskrant.nl{link}"
                
                # Probeer een titel te vinden voor deze specifieke link
                anchor = soup.find('a', href=link)
                title = anchor.get_text().strip() if anchor else "Volkskrant TV Artikel (Titel niet leesbaar)"
                
                if len(title) > 10:
                    articles.append({
                        "title": title, 
                        "link": full_link, 
                        "source": "Volkskrant TV-Recensie", 
                        "snippet": "Direct gescraped via deep scan."
                    })
                    seen_local.add(link)
                if len(articles) >= 5: break
    except Exception as e:
        print(f"DEBUG: Deep scan VK mislukt: {e}")
    return articles

def get_ai_prioritized_articles(articles):
    prio1_labels = ["Parool: Han Lips", "Trouw: Maaike Bos", "Volkskrant TV-Recensie", "NRC Zap"]
    prio1_list = [a for a in articles if a['source'] in prio1_labels]
    others = [a for a in articles if a['source'] not in prio1_labels]

    if not others:
        return {"prio1": prio1_list, "prio2": [], "prio3": []}
    
    if not GEMINI_KEY:
        return {"prio1": prio1_list, "prio2": others, "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(others)]
    
    prompt = (
        "Sorteer deze media-artikelen:\n"
        "Groep 2: Hard nieuws over TV, radio, kijkcijfers, zenders.\n"
        "Groep 3: Podcasts en lange interviews.\n"
        "STRENG: Verwijder alles wat NIET over media gaat (geen algemene cultuur).\n"
        "JSON: {\"prio2\": [ids], \"prio3\": [ids]}"
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        data = json.loads(re.search(r'\{.*\}', resp.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL).group())
        return {
            "prio1": prio1_list,
            "prio2": [others[i] for i in data.get("prio2", []) if i < len(others)],
            "prio3": [others[i] for i in data.get("prio3", []) if i < len(others)]
        }
    except:
        return {"prio1": prio1_list, "prio2": others, "prio3": []}

def run_scraper():
    all_found, seen_links = [], set()
    
    # 1. Volkskrant Deep Scan
    for art in scrape_volkskrant_direct():
        if art['link'] not in seen_links:
            all_found.append(art); seen_links.add(art['link'])

    # 2. NRC Zap (Blijft via RSS/directe pagina meestal goed gaan)
    try:
        resp = requests.get("https://www.nrc.nl/onderwerp/zap/", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/2026/')):
            link = a['href']
            full_link = f"https://www.nrc.nl{link}" if not link.startswith('http') else link
            if full_link not in seen_links:
                all_found.append({"title": a.get_text().strip(), "link": full_link, "source": "NRC Zap", "snippet": "Nieuws uit NRC Zap"})
                seen_links.add(full_link)
    except: pass

    # 3. RSS Feeds (Vangnet)
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
                title = clean_text(t_match.group(1)) if t_match else "Geen titel"
                
                # Check voor Volkskrant TV in RSS
                if "volkskrant.nl" in link and "/televisie/" in link:
                    all_found.append({"title": title, "link": link, "source": "Volkskrant TV-Recensie", "snippet": "Gevonden via RSS vanger."})
                    seen_links.add(link)
                # Overige logica (Han Lips, Maaike Bos, etc.)
                elif "han-lips" in link or "han lips" in title.lower():
                    all_found.append({"title": title, "link": link, "source": "Parool: Han Lips", "snippet": "TV-column Parool"})
                    seen_links.add(link)
                elif "maaike-bos" in link or "maaike bos" in title.lower():
                    all_found.append({"title": title, "link": link, "source": "Trouw: Maaike Bos", "snippet": "TV-recensie Trouw"})
                    seen_links.add(link)
        except: continue
            
    return get_ai_prioritized_articles(all_found)

def build_html_section(title, articles, color):
    if not articles: return ""
    html = f"<h3 style='color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px; margin-top: 30px;'>{title}</h3><ul style='padding:0;'>"
    for art in articles:
        html += f"""<li style='margin-bottom: 20px; list-style: none; border-left: 4px solid {color}; padding-left: 15px;'>
            <strong style='font-size: 15px;'>[{art['source']}] {art['title']}</strong><br>
            <a href='https://archive.is/{art['link']}' style='color: #3498db; text-decoration: none; font-size: 12px; font-weight: bold;'>🔓 Lees artikel</a></li>"""
    return html + "</ul>"

if __name__ == "__main__":
    prio_data = run_scraper()
    content = build_html_section("⭐ Belangrijkste artikelen", prio_data['prio1'], "#e67e22")
    content += build_html_section("📺 Media Nieuws", prio_data['prio2'], "#2980b9")
    content += build_html_section("🎧 Podcasts & Achtergrond", prio_data['prio3'], "#7f8c8d")
    
    if content:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}", "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'>{content}</body></html>"})
