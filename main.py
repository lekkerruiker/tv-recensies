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

DIRECT_SCRAPE_URLS = [
    ("NRC Zap", "https://www.nrc.nl/onderwerp/zap/"),
    ("Volkskrant TV-Recensie", "https://www.volkskrant.nl/televisie/"),
    ("NRC Cultuur", "https://www.nrc.nl/index/cultuur/")
]

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def has_exact_word(word_list, text):
    text = text.lower()
    for word in word_list:
        if re.search(rf'\b{re.escape(word.lower())}\b', text):
            return True
    return False

def scrape_direct_pages():
    articles = []
    today_str = datetime.now().strftime("/%Y/%m/%d/")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("/%Y/%m/%d/")
    
    print(f"DEBUG: Start direct scrape...")

    for source_label, url in DIRECT_SCRAPE_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                found_on_page = 0
                
                # We zoeken breed naar alle links die naar artikelen kunnen leiden
                for a in soup.find_all('a', href=True):
                    link = a['href']
                    title = a.get_text().strip()
                    
                    # Skip hele korte teksten (menu-items)
                    if len(title) < 15: continue 
                    
                    full_link = link if link.startswith('http') else f"https://www.{'nrc.nl' if 'nrc' in url else 'volkskrant.nl'}{link}"

                    # VOLKSKRANT TELEVISIE: We pakken alles wat /televisie/ in de URL heeft
                    if "volkskrant.nl/televisie" in url:
                        # Filter op patronen die op artikelen lijken, skip de sectie-header zelf
                        if "/televisie/" in link and len(link) > 30: 
                            articles.append({"title": title, "link": full_link, "source": source_label, "snippet": "Direct van de TV-sectie."})
                            found_on_page += 1
                            print(f"DEBUG: VK Gevonden: {title}")
                    
                    # NRC: Datum-check blijft hier belangrijk tegen oude cultuur-bagage
                    elif "nrc.nl" in url:
                        if today_str in link or yesterday_str in link:
                            if source_label == "NRC Cultuur" and not has_exact_word(MEDIA_KEYWORDS, title):
                                continue
                            articles.append({"title": title, "link": full_link, "source": source_label, "snippet": "Direct van NRC."})
                            found_on_page += 1
                    
                    if found_on_page >= 10: break # Iets ruimer pakken
                print(f"DEBUG: {source_label} - {found_on_page} artikelen gevonden.")
        except Exception as e:
            print(f"DEBUG: Fout bij direct scrape {source_label}: {e}")
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
        "Je bent een filter voor een media-expert. Sorteer deze lijst strikt:\n"
        "Groep 2 (NIEUWS): Hard nieuws over TV-zenders, streaming, radio, kijkcijfers en presentatoren.\n"
        "Groep 3 (OVERIG): Media-gerelateerde podcasts, achtergrondverhalen over de media-industrie en diepte-interviews.\n"
        "VERWIJDER STRENG: Boeken, theater, musea, concerten en algemene cultuur zonder link naar TV of Radio.\n"
        "Geef ENKEL JSON: {\"prio2\": [ids], \"prio3\": [ids]}"
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_response = resp.json()['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(re.search(r'\{.*\}', raw_response, re.DOTALL).group())
        return {
            "prio1": prio1_list,
            "prio2": [others[i] for i in data.get("prio2", []) if i < len(others)],
            "prio3": [others[i] for i in data.get("prio3", []) if i < len(others)]
        }
    except:
        return {"prio1": prio1_list, "prio2": others, "prio3": []}

def run_scraper():
    all_found, seen_links = [], set()
    
    # 1. Directe pagina's
    for art in scrape_direct_pages():
        if art['link'] not in seen_links:
            all_found.append(art)
            seen_links.add(art['link'])

    # 2. RSS Feeds
    EXCLUDE_KEYWORDS = ['maak kans', 'winactie', 'tickets', 'kaarten voor', 'prijsvraag']
    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            for item in items:
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                if not (t_match and l_match): continue
                title, link = clean_text(t_match.group(1)), l_match.group(1).strip()
                
                if link in seen_links: continue
                
                desc_match = re.search(r'<(?:description|content:encoded|summary)>(.*?)</(?:description|content:encoded|summary)>', item, re.DOTALL)
                snippet = clean_text(desc_match.group(1)) if desc_match else ""
                full_lower = (title + " " + snippet + " " + link).lower()

                if any(bad in title.lower() for bad in EXCLUDE_KEYWORDS): continue
                
                keep, source_label = False, name
                has_media_keyword = has_exact_word(MEDIA_KEYWORDS, title) or has_exact_word(MEDIA_KEYWORDS, snippet)

                # Labels forceren
                if "volkskrant.nl/televisie" in link.lower():
                    source_label, keep = "Volkskrant TV-Recensie", True
                elif name == "Parool" and ("han-lips" in link.lower() or "han lips" in full_lower):
                    source_label, keep = "Parool: Han Lips", True
                elif name == "Trouw" and ("maaike-bos" in link.lower() or "maaike bos" in full_lower):
                    source_label, keep = "Trouw: Maaike Bos", True
                elif ("/podcast/" in link.lower() or "/podcasts/" in link.lower()) and has_media_keyword:
                    source_label, keep = f"{name} Podcast", True
                elif name == "Telegraaf" and "entertainment/media" in link.lower():
                    source_label, keep = "Telegraaf Media", True
                elif has_media_keyword:
                    keep = True

                if keep:
                    all_found.append({"title": title, "link": link, "source": source_label, "snippet": snippet})
                    seen_links.add(link)
        except: continue
            
    return get_ai_prioritized_articles(all_found)

def build_html_section(title, articles, color):
    if not articles: return ""
    html = f"<h3 style='color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px; margin-top: 30px;'>{title}</h3><ul style='padding:0;'>"
    for art in articles:
        archive_link = f"https://archive.is/{art['link']}"
        html += f"""<li style='margin-bottom: 20px; list-style: none; border-left: 4px solid {color}; padding-left: 15px;'>
            <strong style='font-size: 15px;'>[{art['source']}] {art['title']}</strong><br>
            <p style='margin: 4px 0; color: #555; font-size: 14px;'>{art['snippet'][:160]}...</p>
            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 12px; font-weight: bold;'>🔓 Lees artikel</a></li>"""
    return html + "</ul>"

if __name__ == "__main__":
    prio_data = run_scraper()
    totaal = len(prio_data['prio1']) + len(prio_data['prio2']) + len(prio_data['prio3'])
    
    if totaal > 0:
        content = build_html_section("⭐ Belangrijkste artikelen", prio_data['prio1'], "#e67e22")
        content += build_html_section("📺 Media Nieuws", prio_data['prio2'], "#2980b9")
        content += build_html_section("🎧 Podcasts & Achtergrond", prio_data['prio3'], "#7f8c8d")
        
        requests.post(
            "https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'>{content}</body></html>"
            }
        )
