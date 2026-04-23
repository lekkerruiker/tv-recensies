import os
import requests
import feedparser
from datetime import datetime, timedelta
import json
import re
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

# Specifieke URL patronen voor recensies (Prio 1)
PRIO1_URL_PATTERNS = [
    r'/televisie/',
    r'/zap[^a-z]',  # ZAP maar niet 'zapper' of 'zapping'
    r'/recensie',
    r'/media.*recensie',
    r'han-lips',
    r'maaike-bos',
    r'marcel-peereboom-voller',
    r'marcel-bekijkt'
]

# Auteurs van recensies
RECENSIE_AUTEURS = [
    'han lips', 'maaike bos', 'marcel peereboom voller',
    'angela de jong', 'marc van der linden'
]

# Keywords voor media-filtering met word boundaries
MEDIA_KEYWORDS_REGEX = [
    r'\btv\b', r'\btelevisie\b', r'\bradio\b', r'\bkijkcijfer', 
    r'\bpodcast\b', r'\bstreaming\b', r'\bnetflix\b', r'\bvideoland\b', 
    r'\bnpo\b', r'\brtl\b', r'\bsbs\b', r'\bomroep', 
    r'\bvandaag inside\b', r'\bjinek\b', r'\blubach\b', 
    r'\bpresentator', r'\bprogramma', r'\bzender\b', r'\buitzending', 
    r'\bserie[^n]\b', r'\btalkshow\b', r'\bavrotros\b', r'\bbnnvara\b', 
    r'\bkro-ncrv\b', r'\bmax\b', r'\bvpro\b', r'\brego\b'
]

# TV Programma's (hele woorden)
TV_PROGRAMS = [
    'vandaag inside', 'jinek', 'beau', 'renze', 'lubach', 
    'zondag met lubach', 'nieuwsuur', 'pauw', 'humberto', 'rtl nieuws',
    'nos journaal', 'een vandaag', 'op1', 'khalid en sophie',
    'boer zoekt vrouw', 'the voice', 'wie is de mol', 'heel holland bakt',
    'married at first sight', 'temptation island', 'gooische vrouwen',
    'mocro maffia', 'undercover', 'penoza'
]

# Keywords die uitgesloten moeten worden
EXCLUDE_KEYWORDS = [
    r'\bboek\b', r'\broman\b', r'\bthriller\b', r'\bbiografie\b', r'\bbestseller\b',
    r'\btheater\b', r'\btoneelstuk\b', r'\bmusical\b', r'\bopera\b', r'\bballet\b',
    r'\bmuseum\b', r'\btentoonstelling\b', r'\bexpo\b', r'\bgalerie\b',
    r'\bconcert\b', r'\bfestival\b', r'\bpodium\b',
    r'\bfilm\b', r'\bbioscoop\b', r'\bcinema\b',
    r'\bpolitiek\b', r'\bverkiezing', r'\bkabinet\b', r'\btweede kamer\b',
    r'\bklimaat\b', r'\benergie\b', r'\bmilieu\b', r'\bnatuur\b',
    r'\binpoldering\b', r'\bpolder\b', r'\bmarkermeer\b'
]

def is_from_yesterday_or_today(published_date) -> bool:
    """Check of artikel van gisteren of vandaag is (ruimere marge)"""
    try:
        if not published_date:
            return True
        
        if isinstance(published_date, str):
            pub_date = datetime.strptime(published_date, '%a, %d %b %Y %H:%M:%S %z')
        else:
            pub_date = datetime(*published_date[:6])
        
        # Accepteer artikelen van afgelopen 36 uur
        cutoff = datetime.now() - timedelta(hours=36)
        return pub_date.replace(tzinfo=None) >= cutoff
    except:
        return True

def is_media_related(title: str, url: str) -> bool:
    """Check of artikel over media/TV/radio gaat met word boundaries"""
    text = f"{title.lower()} {url.lower()}"
    
    # Eerst exclusions checken (met word boundaries)
    for pattern in EXCLUDE_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    
    # Check TV programma's (exacte matches)
    for program in TV_PROGRAMS:
        if program.lower() in text:
            return True
    
    # Check media keywords met regex word boundaries
    for pattern in MEDIA_KEYWORDS_REGEX:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False

def is_priority_1(url: str, title: str, source: str) -> bool:
    """Check of dit een recensie is (Prio 1)"""
    url_lower = url.lower()
    title_lower = title.lower()
    
    # Check URL patronen met regex
    for pattern in PRIO1_URL_PATTERNS:
        if re.search(pattern, url_lower):
            print(f"    🎯 Prio 1 match (URL pattern): {title[:50]}")
            return True
    
    # Check op recensie-woorden in titel
    recensie_signals = [
        r'\brecensie\b', r'\bbekeken\b', r'\bzap:', r'\btv-recensie\b',
        r'\bbesproken\b', r'\bgetest\b'
    ]
    for signal in recensie_signals:
        if re.search(signal, title_lower):
            print(f"    🎯 Prio 1 match (titel signal): {title[:50]}")
            return True
    
    # Check op bekende recensenten
    for auteur in RECENSIE_AUTEURS:
        if auteur in title_lower or auteur in url_lower:
            print(f"    🎯 Prio 1 match (auteur {auteur}): {title[:50]}")
            return True
    
    # Specifieke checks per bron
    if source == "NRC" and "zap" in url_lower:
        print(f"    🎯 Prio 1 match (NRC Zap): {title[:50]}")
        return True
    
    if source == "Volkskrant" and "/televisie/" in url_lower:
        print(f"    🎯 Prio 1 match (VK Televisie): {title[:50]}")
        return True
    
    return False

def scrape_feeds() -> Dict[str, List[Dict]]:
    """Haal artikelen op uit alle feeds"""
    articles = {
        'prio1': [],
        'prio2': [],
        'potential': []
    }
    seen_links = set()
    
    for source, feed_url in FEEDS.items():
        print(f"\n📰 Scannen: {source}...")
        
        try:
            feed = feedparser.parse(feed_url)
            processed = 0
            
            for entry in feed.entries:
                link = entry.get('link', '')
                if link in seen_links or not link:
                    continue
                
                title = entry.get('title', '').strip()
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                
                # Filter op datum (ruimer: laatste 36 uur)
                if not is_from_yesterday_or_today(published):
                    continue
                
                processed += 1
                
                # Filter op media-gerelateerd
                if not is_media_related(title, link):
                    continue
                
                article = {
                    'title': title,
                    'link': link,
                    'source': source
                }
                
                seen_links.add(link)
                
                # Check of het een recensie is
                if is_priority_1(link, title, source):
                    articles['prio1'].append(article)
                else:
                    articles['potential'].append(article)
            
            print(f"  ✓ {processed} recente artikelen bekeken")
                    
        except Exception as e:
            print(f"  ❌ Fout bij {source}: {e}")
    
    print(f"\n{'='*60}")
    print(f"✅ GEVONDEN:")
    print(f"   ⭐ {len(articles['prio1'])} recensies (Prio 1)")
    print(f"   📋 {len(articles['potential'])} overige media-artikelen")
    print(f"{'='*60}\n")
    
    return articles

def classify_with_ai(articles: List[Dict]) -> Dict[str, List[Dict]]:
    """Laat Gemini de overige artikelen classificeren"""
    if not articles:
        return {'prio2': [], 'prio3': []}
    
    if not GEMINI_KEY:
        print("⚠️  Geen Gemini key, alles naar Prio 2")
        return {'prio2': articles, 'prio3': []}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    input_data = [{"id": i, "title": a['title'], "source": a['source']} 
                  for i, a in enumerate(articles)]
    
    prompt = f"""Classificeer deze Nederlandse TV/Media artikelen in PRECIES 2 categorieën.

PRIO 2 - Belangrijk nieuws (direct relevant):
- Kijkcijfers en TV-ratings
- Nieuwe programma's en seizoenen
- Presentatorwissels en casting
- Zenderbeslissingen (NPO, RTL, SBS)
- Streaming nieuws (Netflix, Videoland releases)
- Radio nieuws en format wijzigingen
- Mediacontracten en deals

PRIO 3 - Achtergrond en diepgang:
- Interviews met makers/presentatoren
- Analyses en opiniestukken over media
- Podcasts over TV/Media
- Media-historische artikelen
- Profielen en portretten

ARTIKELEN:
{json.dumps(input_data, ensure_ascii=False)}

Antwoord ALLEEN met valid JSON zonder markdown formatting:
{{"prio2": [array met id numbers], "prio3": [array met id numbers]}}

Voorbeeld: {{"prio2": [0, 2, 5], "prio3": [1, 3, 4]}}"""

    try:
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        response.raise_for_status()
        
        raw = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        # Clean markdown formatting
        cleaned = raw.replace('```json', '').replace('```', '').strip()
        json_match = json.loads(cleaned)
        
        result = {
            'prio2': [articles[i] for i in json_match.get('prio2', []) if i < len(articles)],
            'prio3': [articles[i] for i in json_match.get('prio3', []) if i < len(articles)]
        }
        
        print(f"🤖 AI classificatie voltooid:")
        print(f"   📺 {len(result['prio2'])} artikelen → Prio 2 (belangrijk nieuws)")
        print(f"   🎧 {len(result['prio3'])} artikelen → Prio 3 (achtergrond)\n")
        
        return result
        
    except Exception as e:
        print(f"❌ AI classificatie mislukt: {e}")
        print("   Fallback: alles naar Prio 2\n")
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
    
    content = section_html("TV Recensies", prio1, "⭐", "#e67e22")
    content += section_html("Media Nieuws", prio2, "📺", "#2980b9")
    content += section_html("Achtergrond & Verdieping", prio3, "🎧", "#7f8c8d")
    
    total = len(prio1) + len(prio2) + len(prio3)
    
    return f"""
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                 padding: 20px; max-width: 800px; margin: 0 auto; background: #ffffff;">
        <h1 style="color: #2c3e50; margin-bottom: 10px;">📺 Media Focus</h1>
        <p style="color: #7f8c8d; margin-bottom: 30px;">
            {datetime.now().strftime('%A %d %B %Y')} • {total} artikelen
        </p>
        {content}
        <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
        <p style="color: #999; font-size: 12px; text-align: center;">
            Automatisch gegenereerd uit Volkskrant, NRC, Telegraaf, Trouw en Het Parool
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
                "subject": f"📺 Media Focus - {datetime.now().strftime('%d %B %Y')}",
                "html": html_content
            },
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        print(f"✅ Email verzonden! (ID: {result.get('id', 'onbekend')})\n")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Email verzenden mislukt: {e}\n")
        return False

def main():
    """Hoofdfunctie"""
    print(f"\n{'='*60}")
    print(f"🚀 MEDIA FOCUS SCRAPER")
    print(f"📅 {datetime.now().strftime('%A %d %B %Y om %H:%M')}")
    print(f"{'='*60}")
    
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
        print("\n⚠️  GEEN ARTIKELEN GEVONDEN")
        print("Mogelijke oorzaken:")
        print("  - Feeds bevatten geen recente artikelen (laatste 36 uur)")
        print("  - Geen artikelen matchen de media-filters")
        print("  - RSS feeds zijn tijdelijk niet beschikbaar\n")
        return
    
    print(f"{'='*60}")
    print(f"📊 TOTAAL: {total} artikelen voor de mail")
    print(f"{'='*60}\n")
    
    html = build_html_email(articles['prio1'], articles['prio2'], articles['prio3'])
    send_email(html)
    
    print(f"{'='*60}")
    print("✅ KLAAR!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
