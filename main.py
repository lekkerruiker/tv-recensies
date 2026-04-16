import os
import requests
import re
from datetime import datetime
import json

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def get_ai_sorted_list(articles):
    """Laat Gemini de volledige lijst sorteren op relevantie voor de TV-sector."""
    if not GEMINI_KEY or not articles:
        return articles
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(articles)]
    
    prompt = (
        "Je bent een gespecialiseerde media-redacteur. Sorteer de onderstaande lijst met artikelen op basis van relevantie voor iemand die in de Nederlandse TV-sector werkt. "
        "GEBRUIK DEZE PRIORITEITEN:\n"
        "1. Hoogste prioriteit: TV-recensies van de Volkskrant en 'Zap' columns van NRC.\n"
        "2. Hoge prioriteit: Nieuws over de NPO, RTL, SBS, talkshows en bekende presentatoren.\n"
        "3. Lagere prioriteit: Algemeen media-nieuws of vage cultuurberichten.\n\n"
        "Geef als antwoord ENKEL een JSON lijst met de ID-nummers terug in de nieuwe volgorde, met ALLE ID's uit de lijst. "
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        raw_response = resp.json()['candidates'][0]['content']['parts'][0]['text']
        ids = json.loads(re.search(r'\[.*\]', raw_response).group())
        return [articles[i] for i in ids if i < len(articles)]
    except Exception as e:
        print(f"AI Sortering mislukt: {e}")
        return articles

def run_scraper():
    all_found = []
    seen_links = set()
    
    # Geoptimaliseerde lijst keywords inclusief de omroepen en sectie-namen
    keywords = [
        'tv', 'televisie', 'omroep', 'npo', 'rtl', 'sbs', 'recensie', 'kijkt', 'zap', 
        'lips', 'fortuin', 'nijkamp', 'talkshow', 'serie', 'mafs', 'avrotros', 
        'powned', 'bnnvara', 'kro-ncrv', 'omroep max', 'wnl', 'vpro', 'human', 
        'ntr', 'omroep zwart', 'eo', '/televisie', '/media'
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
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
                    
                    full_text = (title + " " + link + " " + snippet).lower()
                    if any(k in full_text for k in keywords):
                        all_found.append({
                            "title": title, "link": link, "source": name, "snippet": snippet
                        })
                        seen_links.add(link)
        except: continue
    
    sorted_articles = get_ai_sorted_list(all_found)
    
    results_html = ""
    for i, art in enumerate(sorted_articles, 1):
        archive_link = f"https://archive.is/{art['link']}"
        border_color = "#e67e22" if i <= 5 else "#bdc3c7"
        
        results_html += f"""
        <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid {border_color}; padding-left: 15px;'>
            <strong style='font-size: 16px; color: #2c3e50;'>[{art['source']}] {art['title']}</strong><br>
            <p style='margin: 5px 0; color: #444; font-size: 14px;'>{art['snippet'][:180]}...</p>
            <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 13px; font-weight: bold;'>🔓 Lees op Archive.is</a>
        </li>"""
    return results_html

if __name__ == "__main__":
    content = run_scraper()
    
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"TV & Media Ranglijst: {datetime.now().strftime('%d-%m')}",
            "html": f"""
            <html>
                <body style='font-family:sans-serif; max-width:650px; margin:0 auto; padding:20px;'>
                    <h2 style='color: #e67e22; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📺 TV & Media Overzicht</h2>
                    <p style='color: #7f8c8d; font-style: italic;'>Alle relevante artikelen, gesorteerd op belangrijkheid voor de TV-sector.</p>
                    <ul style='padding: 0;'>{content}</ul>
                </body>
            </html>
            """
        }
    )
