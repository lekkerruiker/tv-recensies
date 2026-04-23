import os
import requests
import feedparser
from datetime import datetime, timedelta
import json
import re
from typing import List, Dict

# --- CONFIGURATIE (ongewijzigd) ---
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "NRC": "https://www.nrc.nl/rss/"
}

# --- VERBETERDE FILTERS ---

# Specifieke URL patronen voor recensies (Prio 1)
# Toegevoegd: bredere patronen voor de Volkskrant en Parool
PRIO1_URL_PATTERNS = [
    r'/televisie', 
    r'/recensie',
    r'/media',
    r'han-lips',
    r'maaike-bos',
    r'marcel-peereboom-voller',
    r'marcel-bekijkt',
    r'tv-column'
]

# Uitgesloten onderwerpen (iets ruimer om Scunthorpe te voorkomen)
EXCLUDE_KEYWORDS = [
    r'\bboek\b', r'\broman\b', r'\btheater\b', r'\btoneelstuk\b', r'\bmusical\b', 
    r'\bmuseum\b', r'\bpolitiek\b', r'\bverkiezing', r'\binpoldering\b', r'\basiel\b'
]

def is_from_yesterday_or_today(entry) -> bool:
    """Check of artikel recent is (laatste 48 uur voor meer marge)"""
    try:
        published = entry.get('published_parsed') or entry.get('updated_parsed')
        if not published: return True
        pub_date = datetime(*published[:6])
        cutoff = datetime.now() - timedelta(hours=48)
        return pub_date >= cutoff
    except:
        return True

def is_media_related(title: str, url: str, source: str) -> bool:
    """Bepaal of het media is. VOORRANG voor specifieke bron/sectie combinaties."""
    text = f"{title.lower()} {url.lower()}"
    
    # 1. VIP Secties: Als het van deze URL's komt, is het ALTIJD media
    if any(pattern in url.lower() for pattern in ['/televisie', '/zap', 'han-lips', 'maaike-bos']):
        return True

    # 2. Harde uitsluiting (alleen als het GEEN VIP sectie is)
    for pattern in EXCLUDE_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    
    # 3. Algemene media trefwoorden
    media_indicators = ['tv', 'televisie', 'radio', 'kijkcijfer', 'omroep', 'seri', 'netflix', 'videoland', 'npo', 'rtl', 'sbs']
    if any(word in text for word in media_indicators):
        return True
        
    return False

def is_priority_1(url: str, title: str, source: str) -> bool:
    """Check of dit de 'Heilige Graal' recensies zijn."""
    url_l = url.lower()
    title_l = title.lower()
    
    # De specifieke vangers
    if "han-lips" in url_l or "han lips" in title_l: return True
    if "maaike-bos" in url_l or "maaike bos" in title_l: return True
    if source == "NRC" and ("/zap" in url_l or "zap:" in title_l): return True
    if source == "Volkskrant" and "/televisie" in url_l: return True
    
    # Algemene recensie signalen
    if any(sig in title_l for sig in ['tv-recensie', 'recensie:', 'bekeken:', 'column:']):
        # Dubbele check: het moet wel over media gaan
        if any(m in url_l or m in title_l for m in ['televisie', 'tv', 'serie', 'programma']):
            return True

    return False

def scrape_feeds() -> Dict[str, List[Dict]]:
    articles = {'prio1': [], 'potential': []}
    seen_links = set()
    
    for source, feed_url in FEEDS.items():
        print(f"Scannen: {source}...")
        try:
            # We gebruiken een timeout en headers om blokkades te voorkomen
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries:
                link = entry.get('link', '')
                if not link or link in seen_links: continue
                
                title = entry.get('title', '').strip()
                
                if not is_from_yesterday_or_today(entry):
                    continue
                
                if is_media_related(title, link, source):
                    art = {'title': title, 'link': link, 'source': source}
                    seen_links.add(link)
                    
                    if is_priority_1(link, title, source):
                        articles['prio1'].append(art)
                    else:
                        articles['potential'].append(art)
        except Exception as e:
            print(f"Fout bij {source}: {e}")
            
    return articles

# --- AI CLASSIFICATIE (Hetzelfde als jouw script, maar met foutafhandeling) ---
def classify_with_ai(articles: List[Dict]) -> Dict[str, List[Dict]]:
    if not articles: return {'prio2': [], 'prio3': []}
    if not GEMINI_KEY: return {'prio2': articles, 'prio3': []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source']} for i, a in enumerate(articles)]
    
    prompt = f"Classificeer deze media-artikelen in 'prio2' (nieuws/kijkcijfers) of 'prio3' (podcasts/interviews). Gooi artikelen die NIET over media gaan weg. JSON output: {{\"prio2\": [ids], \"prio3\": [ids]}}. Lijst: {json.dumps(input_data)}"

    try:
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        raw = response.json()['candidates'][0]['content']['parts'][0]['text']
        cleaned = re.search(r'\{.*\}', raw, re.DOTALL).group()
        json_match = json.loads(cleaned)
        
        return {
            'prio2': [articles[i] for i in json_match.get('prio2', []) if i < len(articles)],
            'prio3': [articles[i] for i in json_match.get('prio3', []) if i < len(articles)]
        }
    except:
        return {'prio2': articles, 'prio3': []}

# --- EMAIL & MAIN (Grotendeels gelijk aan jouw script) ---
def build_html_email(p1, p2, p3):
    # (Houd hier je eigen HTML build functie aan, die ziet er goed uit)
    # Zorg dat de archive.is links erin blijven!
    pass

# ... (rest van je functies: send_email en main)
