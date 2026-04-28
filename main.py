import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

def get_dpg_articles_direct(source, path):
    """Scant de live sectie-pagina van de krant (meest actueel)."""
    articles = []
    url = f"https://www.{source.lower()}.nl/{path}"
    try:
        print(f"Scannen van: {url}")
        r = requests.get(url, headers=HEADERS, timeout=20)
        # We zoeken naar de link-ID (~b...) en de tekst die in de buurt staat
        matches = re.findall(r'href="([^"]+?~b[^"]+?)".*?>(.*?)<', r.text, re.DOTALL)
        
        for link, title in matches:
            # Opschonen titel
            clean_title = re.sub('<[^<]+?>', '', title).strip()
            if len(clean_title) < 10: continue
            
            # Maak link absoluut indien nodig
            full_link = link if link.startswith('http') else f"https://www.{source.lower()}.nl{link}"
            
            # Alleen toevoegen als het een televisie/media artikel is
            if '/televisie' in full_link or '/columns/han-lips' in full_link or any(x in clean_title.lower() for x in ['tv', 'recensie', 'kijkt']):
                if not any(a['link'] == full_link for a in articles):
                    articles.append({'title': clean_title, 'link': full_link, 'source': source})
    except Exception as e:
        print(f"Fout bij {source}: {e}")
    return articles

def main():
    all_articles = []
    seen_links = set()

    # 1. Volkskrant & Parool via de DIRECTE SECTIE (geen sitemap/archief meer)
    all_articles.extend(get_dpg_articles_direct("Volkskrant", "televisie"))
    all_articles.extend(get_dpg_articles_direct("Parool", "televisie"))
    
    # 2. De rest via RSS (NRC, Telegraaf, Trouw)
    RSS_FEEDS = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(requests.get(url, headers=HEADERS, timeout=15).text)
            for entry in feed.entries:
                link = entry.get('link')
                title = entry.get('title', '')
                
                # Check op relevantie
                t_l = (title + link).lower()
                if any(x in t_l for x in ['televisie', 'tv-recensie', 'maaike-bos', 'zap:', 'bekeken:', 'han-lips']):
                    if not any(x in title.lower() for x in ['boek', 'concert', 'stikstof']):
                        all_articles.append({'title': title, 'link': link, 'source': name})
        except: continue

    # Uniek maken en e-mail bouwen
    final_list = []
    for art in all_articles:
        if art['link'] not in seen_links:
            final_list.append(art)
            seen_links.add(art['link'])

    if final_list:
        body = "<h2 style='color:#e67e22; border-bottom:1px solid #e67e22;'>⭐ Dagelijkse Selectie</h2>"
        for art in final_list:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"

        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [EMAIL_RECEIVER], "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", "html": f"<html><body>{body}</body></html>"})
        print(f"Mail verzonden met {len(final_list)} artikelen.")
    else:
        print("Niets gevonden.")

if __name__ == "__main__":
    main()
