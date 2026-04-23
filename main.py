import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# NRC en Telegraaf blijven via de stabiele RSS
RSS_FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Telegraaf": "https://www.telegraaf.nl/rss",
    "Trouw": "https://www.trouw.nl/rss.xml"
}

# Deze headers zijn essentieel: ze laten ons lijken op een echte browser op een Mac
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.google.com/',
    'DNT': '1'
}

def get_dpg_direct(source_name, url):
    """Haalt artikelen op door de HTML direct te lezen, zonder RSS-parser."""
    articles = []
    try:
        print(f"Directe scan van {source_name}: {url}")
        r = requests.get(url, headers=HEADERS, timeout=20)
        # We zoeken naar de typische linkstructuur van DPG (~b...)
        # We pakken een ruimere match voor de titels om niets te missen
        matches = re.findall(r'href="(/[^"]+?~b[^"]+?)".*?>(.*?)<', r.text, re.DOTALL)
        
        for link, title in matches:
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            if len(clean_title) < 15: continue
            
            # De 'Gouden Filter' van onze succesvolle runs:
            if any(x in clean_title.lower() or x in link.lower() for x in ['tv', 'recensie', 'lips', 'weimans', 'kijkt', 'serie', 'docu', 'raymann']):
                full_link = f"https://www.{source_name.lower()}.nl{link}"
                if not any(a['link'] == full_link for a in articles):
                    articles.append({'title': clean_title, 'link': full_link, 'source': source_name})
                    print(f"  Gevonden: {clean_title}")
    except Exception as e:
        print(f"Fout bij {source_name}: {e}")
    return articles

def main():
    all_articles = []
    seen = set()

    # 1. Volkskrant Archief van gisteren (jouw succesvolle methode)
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    all_articles.extend(get_dpg_direct("Volkskrant", f"https://www.volkskrant.nl/archief/{yesterday}"))
    
    # 2. Parool Televisie sectie (direct)
    all_articles.extend(get_dpg_direct("Parool", "https://www.parool.nl/televisie"))

    for a in all_articles: seen.add(a['link'])

    # 3. De overige kranten via RSS
    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(requests.get(url, headers=HEADERS, timeout=15).text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                if not link or link in seen: continue
                
                # Check op relevantie (Prio filter)
                if any(x in title.lower() or x in link.lower() for x in ['tv', 'recensie', 'zap', 'bekeken']):
                    if not any(x in title.lower() for x in ['stikstof', 'oekraïne', 'beurs']):
                        all_articles.append({'title': title, 'link': link, 'source': name})
                        seen.add(link)
        except: continue

    # E-mail verzenden
    body = ""
    if all_articles:
        body += "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in all_articles:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

    if body:
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})
        print("Mail verstuurd!")
    else:
        print("Niets gevonden.")

if __name__ == "__main__":
    main()
