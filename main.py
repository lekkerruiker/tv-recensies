import os
import requests
import feedparser
from datetime import datetime, timedelta
import json
from typing import List, Dict

# --- CONFIGURATIE ---
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

# Specifieke paden die direct naar Prio 1 gaan
PRIO1_URL_PATTERNS = [
    '/televisie',
    '/zap',
    '/recensie',
    '/media/recensie',
    'han-lips',
    'maaike-bos',
    'marcel-peereboom-voller',
    'marcel-bekijkt'
]

# Keywords voor media-filtering
MEDIA_KEYWORDS = [
    'tv', 'televisie', 'radio', 'kijkcijfer', 'podcast', 'streaming',
    'netflix', 'videoland', 'npo', 'rtl', 'sbs', 'omroep',
    'vandaag inside', 'jinek', 'lubach', 'presentator', 'programma',
    'zender', 'uitzending', 'serie', 'talkshow'
]

# Keywords die ons NIET interesseren
EXCLUDE_KEYWORDS = [
    'boek', 'theater', 'museum', 'expo', 'concert', 'film',
    'bioscoop', 'podium', 'musical', 'opera'
]

def is_from_yesterday(published_date) -> bool:
    """Check of artikel van gisteren is"""
    try:
        if not published_date:
            return True  # Als geen datum, neem aan dat het recent is
        
        # Parse publicatiedatum
        if isinstance(published_date, str):
            pub_date = datetime.strptime(published_date, '%a, %d %b %Y %H:%M:%S %z')
        else:
            pub_date = datetime(*published_date[:6])
        
        yesterday = datetime.now() - timedelta(days=1)
        
        # Check of artikel tussen gisteren 00:00 en vandaag 00:00 gepubliceerd is
        return yesterday.date() == pub_date.date()
    except:
        return True  # Bij twijfel meenemen

def is_media_related(title: str, url: str) -> bool:
    """Check of artikel over media/TV/radio gaat"""
    text = f"{title.lower()} {url.lower()}"
    
    # Eerst exclusions checken
    if any(excl in text for excl in EXCLUDE_KEYWORDS):
        return False
    
    # Dan media keywords
    return any(kw in text for kw in MEDIA_KEYWORDS)

def is_priority_1(url: str, title: str) -> bool:
    """Check of dit een recensie is (Prio 1)"""
    url_lower = url.lower()
    title_lower = title.lower()
    
    # Check URL patronen
    if any(pattern in url_lower for pattern in PRIO1_URL_PATTERNS):
        return True
    
    # Check titel voor recensie-signalen
    recensie_signals = ['recensie', 'bekeken', 'zap:', 'tv-recensie']
    return any(signal in title_lower for signal in recensie_signals)

def scrape_feeds() -> Dict[str, List[Dict]]:
    """Haal artikelen op uit alle feeds"""
    articles = {
        'prio1': [],
        'prio2': [],
        'potential': []  # Voor AI classificatie
    }
    seen_links = set()
    
    for source, feed_url in FEEDS.items():
        print(f"📰 Scannen: {source}...")
        
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries:
                link = entry.get('link', '')
                if link in seen_links or not link:
                    continue
                
                title = entry.get('title', '').strip()
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                
                # Filter op datum
                if not is_from_yesterday(published):
                    continue
                
                # Filter op media-gerelateerd
                if not is_media_related(title, link):
                    continue
                
                article = {
                    'title': title,
                    'link': link,
                    'source': source
                }
                
                seen_links.add(link)
                
                # Direct naar Prio 1 als het een recensie is
                if is_priority_1(link, title):
                    articles['prio1'].append(article)
                    print(f"  ⭐ PRIO 1: {title[:60]}...")
                else:
                    articles['potential'].append(article)
                    
        except Exception as e:
            print(f"❌ Fout bij {source}: {e}")
    
    print(f"\n✅ Gevonden: {len(articles['prio1'])} recensies, {len(articles['potential'])} overige artikelen")
    return articles

def classify_with_ai(articles: List[Dict]) -> Dict[str, List[Dict]]:
    """Laat Gemini de overige artikelen classificeren"""
    if not articles:
        return {'prio2': [], 'prio3': []}
    
    if not GEMINI_KEY:
        print("⚠️  Geen Gemini key, alles naar Prio 2")
        return {'prio2': articles, 'prio3': []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    # Maak input data met indices
    input_data = [{"id": i, "title": a['title'], "source": a['source']} 
                  for i, a in enumerate(articles)]
    
    prompt = f"""Classificeer deze Nederlandse media-artikelen in 2 categorieën:

PRIO 2 (belangrijk media-nieuws):
- Kijkcijfers en ratings
- Nieuws over NPO, RTL, SBS, omroepen
- Aankondigingen nieuwe programma's
- Presentatorwissels en personeelszaken
- Streamingdiensten (Netflix, Videoland)
- Radio-nieuws

PRIO 3 (achtergrond):
- Interviews
- Analyses en opiniestukken
- Podcasts over media
- Historische terugblikken

Artikelen: {json.dumps(input_data, ensure_ascii=False)}

Antwoord ALLEEN met JSON in dit formaat:
{{"prio2": [ids], "prio3": [ids]}}"""

    try:
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        response.raise_for_status()
        
        raw = response.json()['candidates'][0]['content']['parts'][0]['text']
        # Extract JSON uit mogelijke markdown formatting
        json_match = json.loads(raw.replace('```json', '').replace('```', '').strip())
        
        result = {
            'prio2': [articles[i] for i in json_match.get('prio2', []) if i < len(articles)],
            'prio3': [articles[i] for i in json_match.get('prio3', []) if i < len(articles)]
        }
        
        print(f"🤖 AI classificatie: {len(result['prio2'])} prio2, {len(result['prio3'])} prio3")
        return result
        
    except Exception as e:
        print(f"❌ AI classificatie mislukt: {e}")
        return {'prio2': articles, 'prio3': []}

def build_html_email(prio1: List, prio2: List, prio3: List) -> str:
    """Genereer HTML email"""
    
    def section_html(title: str, articles: List, emoji: str, color: str) -> str:
        if not articles:
            return ""
        
        html = f"""
        <div style="margin-bottom: 30px;">
            <h2 style="color: {color}; border-bottom: 2px solid {color}; padding-bottom: 8px; margin-bottom: 15px;">
                {emoji} {title} ({len(articles)})
            </h2>
        """
        
        for art in articles:
            html += f"""
            <div style="margin-bottom: 12px; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                <strong style="color: #495057;">[{art['source']}]</strong> 
                {art['title']}
                <br>
                <a href="{art['link']}" style="color: #007bff; text-decoration: none; font-size: 14px;">→ Direct lezen</a>
                <span style="color: #999; margin: 0 8px;">|</span>
                <a href="https://archive.is/{art['link']}" style="color: #6c757d; text-decoration: none; font-size: 14px;">→ Archief</a>
            </div>
            """
        
        html += "</div>"
        return html
    
    content = section_html("Recensies", prio1, "⭐", "#e67e22")
    content += section_html("Media Nieuws", prio2, "📺", "#2980b9")
    content += section_html("Achtergrond", prio3, "🎧", "#7f8c8d")
    
    return f"""
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                 padding: 20px; max-width: 800px; margin: 0 auto; background: #ffffff;">
        <h1 style="color: #2c3e50; margin-bottom: 10px;">Media Focus</h1>
        <p style="color: #7f8c8d; margin-bottom: 30px;">{datetime.now().strftime('%A %d %B %Y')}</p>
        {content}
        <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
        <p style="color: #999; font-size: 12px; text-align: center;">
            Dit overzicht is automatisch gegenereerd uit NL krantenfeeds
        </p>
    </body>
    </html>
    """

def send_email(html_content: str) -> bool:
    """Verstuur email via Resend"""
    if not API_KEY or not EMAIL_RECEIVER:
        print("❌ Resend API key of ontvanger email ontbreekt")
        return False
    
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": EMAIL_FROM,
                "to": [EMAIL_RECEIVER],
                "subject": f"📺 Media Focus - {datetime.now().strftime('%d-%m-%Y')}",
                "html": html_content
            },
            timeout=10
        )
        response.raise_for_status()
        print(f"✅ Email verzonden! (ID: {response.json().get('id', 'onbekend')})")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Email verzenden mislukt: {e}")
        return False

def main():
    """Hoofdfunctie"""
    print(f"\n{'='*50}")
    print(f"🚀 Media Focus Scraper")
    print(f"📅 {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    print(f"{'='*50}\n")
    
    # Stap 1: Scrape feeds
    articles = scrape_feeds()
    
    # Stap 2: Classificeer met AI
    if articles['potential']:
        ai_result = classify_with_ai(articles['potential'])
        articles['prio2'] = ai_result['prio2']
        articles['prio3'] = ai_result['prio3']
    else:
        articles['prio2'] = []
        articles['prio3'] = []
    
    # Stap 3: Genereer en verstuur email
    total = len(articles['prio1']) + len(articles['prio2']) + len(articles['prio3'])
    
    if total == 0:
        print("\n⚠️  Geen artikelen gevonden - geen email verzonden")
        return
    
    print(f"\n📊 Totaal {total} artikelen gevonden")
    html = build_html_email(articles['prio1'], articles['prio2'], articles['prio3'])
    send_email(html)
    
    print(f"\n{'='*50}")
    print("✅ Klaar!")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
