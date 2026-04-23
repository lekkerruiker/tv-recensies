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

def scrape_direct_pages():
    articles = []
    # Datumstempels voor NRC (vandaag en gisteren)
    today_str = datetime.now().strftime("/%Y/%m/%d/")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("/%Y/%m/%d/")
    
    # 1. VOLKSKRANT (Geen datumfilter, want die is onbetrouwbaar)
    try:
        vk_url = "https://www.volkskrant.nl/televisie/"
        resp = requests.get(vk_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            count = 0
            for a in soup.find_all('a', href=True):
                link = a['href']
                title = a.get_text().strip()
                if "/televisie/" in link and len(link) > 30 and len(title) > 20:
                    full_link = f"https://www.volkskrant.nl{link}" if not link.startswith('http') else link
                    articles.append({"title": title, "link": full_link, "source": "Volkskrant TV-Recensie", "snippet": "Direct van de TV-sectie."})
                    count += 1
                if count >= 3: break # Alleen de bovenste 3 (meest actueel)
    except: pass

    # 2. NRC ZAP (Strenge datumfilter tegen de lange lijst)
    try:
        nrc_url = "https://www.nrc.nl/onderwerp/zap/"
        resp = requests.get(nrc_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            seen_titles = set()
            count = 0
            for a in soup.find_all('a', href=True):
                link = a['href']
                title = a.get_text().strip()
                # Check op datum in URL EN of we de titel vandaag al gezien hebben
                if (today_str in link or yesterday_str in link) and len(title) > 15:
                    if title not in seen_titles:
                        full_link = f"https://www.nrc.nl{link}" if not link.startswith('http') else link
                        articles.append({"title": title, "link": full_link, "source": "NRC Zap", "snippet": "Dagelijkse Zap-column."})
                        seen_titles.add(title)
                        count += 1
                if count >= 3: break
    except: pass

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
        "Sorteer media-artikelen:\n"
        "Groep 2: Hard nieuws (TV, radio, kijkcijfers).\n"
        "Groep 3: Achtergrond en podcasts.\n"
        "STRENG: Verwijder alles wat niet over media gaat.\n"
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
    
    # 1. Belangrijkste artikelen (VK & NRC)
    for art in scrape_direct_pages():
        if art['link'] not in seen_links:
            all_found.append(art); seen_links.add(art['link'])

    # 2. RSS Feeds (Vangnet voor anderen)
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
                full_lower = (title + " " + link).lower()

                # Prio 1 vangers
                if name == "Parool" and ("han-lips" in link or "han lips" in full_lower):
                    all_found.append({"title": title, "link": link, "source": "Parool: Han Lips", "snippet": "TV-column Parool"})
                    seen_links.add(link)
                elif name == "Trouw" and ("maaike-bos" in link or "maaike bos" in full_lower):
                    all_found.append({"title": title, "link": link, "source": "Trouw: Maaike Bos", "snippet": "TV-recensie Trouw"})
                    seen_links.add(link)
                elif any(word in full_lower for word in MEDIA_KEYWORDS):
                    source_label = f"{name} Podcast" if "/podcast" in link else name
                    all_found.append({"title": title, "link": link, "source": source_label, "snippet": "Gevonden via RSS."})
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
