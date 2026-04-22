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

CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong']

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

def scrape_nrc_media():
    articles = []
    urls = [
        ("NRC Zap", "https://www.nrc.nl/onderwerp/zap/"),
        ("NRC Cultuur", "https://www.nrc.nl/index/cultuur/")
    ]
    today_str = datetime.now().strftime("/%Y/%m/%d/")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("/%Y/%m/%d/")
    
    for source_label, url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for a in soup.find_all('a', class_='nmt-item__link'):
                    title = a.get_text().strip()
                    link = a['href']
                    if today_str in link or yesterday_str in link:
                        if not link.startswith('http'):
                            link = "https://www.nrc.nl" + link
                        if source_label == "NRC Zap" or has_exact_word(MEDIA_KEYWORDS, title):
                            articles.append({"title": title, "link": link, "source": source_label, "snippet": f"Nieuws uit {source_label}"})
        except Exception as e:
            print(f"Fout bij scrapen {source_label}: {e}")
    return articles

def get_ai_prioritized_articles(articles):
    if not GEMINI_KEY or not articles:
        return {"prio1": articles, "prio2": [], "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(articles)]
    
    prompt = (
        "Classificeer deze nieuwsartikelen voor een media-expert in DRIE groepen:\n\n"
        "Groep 1 (ABSOLUTE PRIO): Alleen TV-recensies van de Volkskrant, NRC Zap, Han Lips (Parool) of Maaike Bos (Trouw).\n"
        "Groep 2 (MEDIA NIEUWS): Hard nieuws over TV-zenders (NPO, RTL, SBS), kijkcijfers, talkshows en media-ontwikkelingen.\n"
        "Groep 3 (OVERIG): Alle podcasts (ook die van Telegraaf/Trouw), achtergrondverhalen, radio-items en overige media-artikelen.\n\n"
        "Belangrijk: Podcasts horen NOOIT in Groep 1 of 2. Alleen de 4 genoemde recensenten in Groep 1.\n"
        "Geef ENKEL JSON terug: {\"prio1\": [ids], \"prio2\": [ids], \"prio3\": [ids]}"
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_text = resp.json()['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group())
        
        result = {"prio1": [], "prio2": [], "prio3": []}
        for key in result.keys():
            if key in data:
                result[key] = [articles[i] for i in data[key] if i < len(articles)]
        return result
    except Exception as e:
        print(f"AI Error: {e}")
        return {"prio1": articles, "prio2": [], "prio3": []}

def run_scraper():
    all_found = []
    seen_links = set()
    
    for art in scrape_nrc_media():
        if art['link'] not in seen_links:
            all_found.append(art)
            seen_links.add(art['link'])

    EXCLUDE_KEYWORDS = ['maak kans', 'winactie', 'tickets', 'kaarten voor', 'prijsvraag']

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            for item in items:
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                if not (t_match and l_match): continue
                
                title = clean_text(t_match.group(1))
                link = l_match.group(1).strip()
                if link in seen_links: continue

                desc_match = re.search(r'<(?:description|content:encoded|summary)>(.*?)</(?:description|content:encoded|summary)>', item, re.DOTALL)
                snippet = clean_text(desc_match.group(1)) if desc_match else ""
                full_lower = (title + " " + snippet + " " + link).lower()

                if any(bad in title.lower() for bad in EXCLUDE_KEYWORDS): continue

                keep = False
                source_label = name
                has_critic = any(c in full_lower for c in CRITICS)
                has_media_keyword = has_exact_word(MEDIA_KEYWORDS, title) or has_exact_word(MEDIA_KEYWORDS, snippet)

                if name == "Parool" and ("han-lips" in link.lower() or "han lips" in full_lower):
                    source_label, keep = "Parool: Han Lips", True
                elif name == "Trouw" and ("maaike-bos" in link.lower() or "maaike bos" in full_lower):
                    source_label, keep = "Trouw: Maaike Bos", True
                elif name == "Trouw" and "/podcasts/" in link.lower():
                    source_label, keep = "Trouw Podcast", True
                elif name == "Volkskrant" and ("/televisie/" in link.lower() or "tv-recensie" in full_lower):
                    source_label, keep = "Volkskrant TV-Recensie", True
                elif name == "Telegraaf" and "/podcast/" in link.lower():
                    source_label, keep = "Telegraaf Podcast", True
                elif name == "Telegraaf" and "entertainment/media" in link.lower():
                    source_label, keep = "Telegraaf Media", True

                if not keep:
                    if name == "Volkskrant" and "/cultuur-media/" in link.lower() and has_media_keyword:
                        keep = True
                    elif name == "Parool" and has_media_keyword:
                        keep = True
                    elif has_media_keyword or has_critic:
                        keep = True

                if any(bad in title.lower() for bad in ['gaza', 'soedan', 'oekraïne', 'pkn']) and not has_critic:
                    keep = False

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
        html += f"""
        <li style='margin-bottom: 20px; list-style: none; border-left: 4px solid {color}; padding-left: 15px;'>
            <strong style='font-size: 15px;'>[{art['source']}] {art['title']}</strong><br>
            <p style='margin: 4px 0; color: #555; font-size: 14px;'>{art['snippet'][:160]}...</p>
            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 12px; font-weight: bold;'>🔓 Lees artikel</a>
        </li>"""
    return html + "</ul>"

if __name__ == "__main__":
    prio_data = run_scraper()
    if any(prio_data.values()):
        content_html = build_html_section("⭐ Dagelijkse Kost (Recensies)", prio_data['prio1'], "#e67e22")
        content_html += build_html_section("📺 Media Nieuws", prio_data['prio2'], "#2980b9")
        content_html += build_html_section("🎧 Podcasts & Achtergrond", prio_data['prio3'], "#7f8c8d")

        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER],
                "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'>{content_html}</body></html>"
            }
        )
