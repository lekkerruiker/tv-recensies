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
    urls = [("NRC Zap", "https://www.nrc.nl/onderwerp/zap/"), ("NRC Cultuur", "https://www.nrc.nl/index/cultuur/")]
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
                        if not link.startswith('http'): link = "https://www.nrc.nl" + link
                        articles.append({"title": title, "link": link, "source": source_label, "snippet": f"Nieuws uit {source_label}"})
        except: pass
    return articles

def get_ai_prioritized_articles(articles):
    # Prio 1 labels die we hardcoded als belangrijkste markeren
    prio1_labels = ["Parool: Han Lips", "Trouw: Maaike Bos", "Volkskrant TV-Recensie", "NRC Zap"]
    
    prio1_list = [a for a in articles if a['source'] in prio1_labels]
    others = [a for a in articles if a['source'] not in prio1_labels]

    if not GEMINI_KEY or not others:
        return {"prio1": prio1_list, "prio2": others, "prio3": []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(others)]
    
    prompt = (
        "Classificeer deze media-artikelen:\n"
        "Groep 2 (NIEUWS): Hard nieuws over zenders (RTL, NPO), kijkcijfers, talkshows, media-industrie.\n"
        "Groep 3 (OVERIG): Achtergronden, interviews en podcasts.\n"
        "STRENG: Verwijder alles wat niet over media gaat.\n"
        "Geef ENKEL JSON: {\"prio2\": [ids], \"prio3\": [ids]}"
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        data = json.loads(re.search(r'\{.*\}', resp.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL).group())
        return {
            "prio1": prio1_list,
            "prio2": [others[i] for i in data.get("prio2", []) if i < len(others)],
            "prio3": [others[i] for i in data.get("prio3", []) if i < len(others)]
