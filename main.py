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

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def scrape_direct_pages():
    articles = []
    today_str = datetime.now().strftime("/%Y/%m/%d/")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("/%Y/%m/%d/")
    
    # 1. VOLKSKRANT TV (We pakken simpelweg de bovenste koppen van de pagina)
    try:
        vk_url = "https://www.volkskrant.nl/televisie/"
        resp = requests.get(vk_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            count = 0
            # Zoek alle links in de hoofdkolom die op artikelen lijken
            for a in soup.find_all('a', href=True):
                link = a['href']
                title = a.get_text().strip()
                # Artikelen op VK hebben vaak een specifieke structuur (~b...)
                if "/televisie/" in link and len(title) > 20:
                    full_link = f"https://www.volkskrant.nl{link}" if not link.startswith('http') else link
                    articles.append({
                        "title": title, 
                        "link": full_link, 
                        "source": "Volkskrant TV-Recensie", 
                        "snippet": "Gescraped van de TV-sectie."
                    })
                    count += 1
                if count >= 6: break # Pak de top 6, de AI filtert de rest
    except: pass

    # 2. NRC ZAP (Focus op vandaag/gisteren)
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
                    articles.append({"title": title, "link": full_link, "source": "NRC Zap", "snippet": "Zap-sectie NRC."})
                    count += 1
                if count >= 3: break
    except: pass

    return articles

def get_ai_prioritized_articles(articles):
    # Definieer wat sowieso Prio 1 is op basis van bron/label
    prio1_labels = ["Parool: Han Lips", "Trouw: Maaike Bos", "Volkskrant TV-Recensie", "NRC Zap"]
    prio1_list = [a for a in articles if a['source'] in prio1_labels]
    others = [a for a in articles if a['source'] not in prio1_labels]

    if not others:
        return {"prio1": prio1_list, "prio2": [], "prio3": []}
    
    # Laat Gemini het zware werk doen voor de rest
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(others)]
    
    prompt = (
        "Je bent een expert media-analist. Bekijk de titels en sorteer ze:\n"
        "Groep 2 (Media Nieuws): Hard nieuws over TV, radio, streamingcijfers, presentatoren en zenders.\n"
        "Groep 3 (Verdieping): Media-podcasts, lange interviews met makers, en achtergrondverhalen over de industrie.\n"
        "VERWIJDER STRENG: Alles wat NIET met media (TV/Radio/Streaming) te maken heeft. Geen algemene cultuur, boeken of politiek.\n"
        f"Lijst: {json.dumps(input_data)}\n"
        "Antwoord enkel met JSON: {\"prio2\": [ids], \"prio3\": [ids]}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        res_text = resp.json()['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(re.search(r'\{.*\}', res_text, re.DOTALL).group())
        return {
            "prio1": prio1_list,
            "prio2": [others[i] for i in data.get("prio2", []) if i < len(others)],
            "prio3": [others[i] for i in data.get("prio3", []) if i < len(others)]
        }
    except:
        # Bij fout: stuur alles mee in Prio 2 zodat we niets missen
        return {"prio1": prio1_list, "prio2": others, "prio3": []}

def run_scraper():
    all_found, seen_links = [], set()
    
    # 1. Directe vangers (Prio 1 kandidaten)
    for art in scrape_direct_pages():
        if art['link'] not in seen_links:
            all_found.append(art); seen_links.add(art['link'])

    # 2. RSS Feeds
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
                full_lower = (title + " " + link).lower()

                # Specifieke kolommen herkennen
                if "han-lips" in link or "han lips" in full_lower:
                    all_found.append({"title": title, "link": link, "source": "Parool: Han Lips", "snippet": "TV-column"})
                    seen_links.add(link)
                elif "maaike-bos" in link or "maaike bos" in full_lower:
                    all_found.append({"title": title, "link": link, "source": "Trouw: Maaike Bos", "snippet": "TV-recensie"})
                    seen_links.add(link)
                elif "volkskrant.nl/televisie" in link: # Vangnet voor VK TV in RSS
                    all_found.append({"title": title, "link": link, "source": "Volkskrant TV-Recensie", "snippet": "Gevonden via RSS."})
                    seen_links.add(link)
                else:
                    # Alles wat overblijft gaat naar de AI voor filtering
                    all_found.append({"title": title, "link": link, "source": name, "snippet": "RSS feed item."})
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
    
    if any(prio_data.values()):
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'>{content}</body></html>"
            })
