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

def scrape_nrc_zap():
    """Scrape NRC Zap en filter op datum (afgelopen 24-48 uur)."""
    articles = []
    url = "https://www.nrc.nl/onderwerp/zap/"
    
    # We kijken naar vandaag en gisteren om zeker te zijn dat we de laatste recensie hebben
    today_str = datetime.now().strftime("/%Y/%m/%d/")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("/%Y/%m/%d/")
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', class_='nmt-item__link'):
                title = a.get_text().strip()
                link = a['href']
                
                # Check of de URL van vandaag of gisteren is
                if today_str in link or yesterday_str in link:
                    if not link.startswith('http'):
                        link = "https://www.nrc.nl" + link
                    
                    articles.append({
                        "title": title,
                        "link": link,
                        "source": "NRC",
                        "snippet": "Nieuwste NRC Zap TV-recensie"
                    })
    except Exception as e:
        print(f"Fout bij scrapen NRC: {e}")
    return articles

def get_ai_sorted_list(articles):
    if not GEMINI_KEY or not articles:
        return articles
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source'], "snippet": a['snippet'][:100]} for i, a in enumerate(articles)]
    
    prompt = (
        "Sorteer deze media-artikelen voor een TV-professional. "
        "PRIORITEIT 1: TV-recensies (Maaike Bos, Han Lips, NRC Zap, Volkskrant recensies). "
        "PRIORITEIT 2: Nieuws over NPO, RTL, SBS, talkshows en Tina Nijkamp. "
        "Verwijder dubbele onderwerpen of ruis. Geef ENKEL de JSON lijst met ID's terug."
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_text = resp.json()['candidates'][0]['content']['parts'][0]['text']
        ids = json.loads(re.search(r'\[.*\]', raw_text).group())
        return [articles[i] for i in ids if i < len(articles)]
    except:
        return articles

def run_scraper():
    all_found = []
    seen_links = set()
    
    # 1. NRC via scraping met datum-filter
    for art in scrape_nrc_zap():
        if art['link'] not in seen_links:
            all_found.append(art)
            seen_links.add(art['link'])

    # 2. Andere kranten via RSS
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong']

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
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

                    keep = False
                    if name == "Trouw" and "maaike bos" in full_lower: keep = True
                    elif name == "Parool" and "han-lips" in link.lower(): keep = True
                    elif name == "Volkskrant" and "televisie" in link.lower(): keep = True
                    elif name == "Telegraaf" and "entertainment/media" in link.lower(): keep = True
                    else:
                        if any(word in title.lower() for word in ['talkshow', 'npo', 'rtl', 'sbs', 'kijkcijfer']) or any(c in title.lower() for c in CRITICS):
                            keep = True

                    if keep:
                        all_found.append({"title": title, "link": link, "source": name, "snippet": snippet})
                        seen_links.add(link)
        except: continue
    
    return get_ai_sorted_list(all_found)

if __name__ == "__main__":
    articles = run_scraper()
    if articles:
        results_html = ""
        for i, art in enumerate(articles, 1):
            archive_link = f"https://archive.is/{art['link']}"
            border = "#e67e22" if i <= 5 else "#bdc3c7"
            results_html += f"""
            <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid {border}; padding-left: 15px;'>
                <strong style='font-size: 15px; color: #2c3e50;'>[{art['source']}] {art['title']}</strong><br>
                <p style='margin: 4px 0; color: #555; font-size: 14px;'>{art['snippet'][:160]}...</p>
                <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 12px; font-weight: bold;'>🔓 Lees artikel</a>
            </li>"""

        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, "to": [EMAIL_RECEIVER],
                "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}",
                "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;'><h2>📺 TV & Media Overzicht</h2><ul style='padding:0;'>{results_html}</ul></body></html>"
            }
        )
