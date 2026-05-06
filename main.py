import os
import requests
import feedparser
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# Feeds voor Volkskrant en Trouw
VK_FEEDS = [
    "https://www.google.nl/alerts/feeds/04781440717054478383/4321423776390191439", # Televisie
    "https://www.google.nl/alerts/feeds/04781440717054478383/11932785620654586752"  # Kijkkunde
]
TROUW_FEED = "https://www.google.nl/alerts/feeds/04781440717054478383/9898575911905288324"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

def get_nrc():
    """NRC: Via de website."""
    articles = []
    try:
        url = "https://www.nrc.nl/onderwerp/zap/"
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        target_dates = [
            datetime.now().strftime('%Y/%m/%d'),
            (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
        ]
        for a in soup.find_all('a', href=True):
            link = a['href']
            if "/nieuws/" in link and any(d in link for d in target_dates):
                full_url = f"https://www.nrc.nl{link}" if link.startswith('/') else link
                title = a.get_text().strip()
                if len(title) > 15:
                    articles.append({'title': title, 'link': full_url, 'source': 'NRC'})
    except: pass
    return articles

def get_volkskrant_via_alerts():
    """Volkskrant: Filtert streng op /televisie/."""
    articles = []
    for feed_url in VK_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = re.sub('<[^<]+?>', '', entry.title).replace(" - de Volkskrant", "").strip()
                raw_link = entry.link
                actual_link = raw_link
                if "url=" in raw_link:
                    match = re.search(r'url=(https?://[^&]+)', raw_link)
                    if match: actual_link = match.group(1)

                if "volkskrant.nl/televisie/" in actual_link.lower():
                    articles.append({'title': title, 'link': actual_link, 'source': 'Volkskrant'})
        except: pass
    return articles

def get_trouw_via_alerts():
    """Trouw: Filtert streng op /cultuur-media/."""
    articles = []
    try:
        feed = feedparser.parse(TROUW_FEED)
        for entry in feed.entries:
            # Titel opschonen (Google rommel en sitenaam verwijderen)
            title = re.sub('<[^<]+?>', '', entry.title).replace(" - Trouw", "").strip()
            
            # Echte link uit Google redirect vissen
            raw_link = entry.link
            actual_link = raw_link
            if "url=" in raw_link:
                match = re.search(r'url=(https?://[^&]+)', raw_link)
                if match:
                    actual_link = match.group(1)

            # STRIKTE FILTER voor Trouw
            if "trouw.nl/cultuur-media/" in actual_link.lower():
                articles.append({
                    'title': title,
                    'link': actual_link,
                    'source': 'Trouw'
                })
    except Exception as e:
        print(f"Fout bij Trouw feed: {e}")
    return articles

def get_rss_articles(source, feed_url, path_keyword):
    """Parool & Telegraaf: Via RSS."""
    articles = []
    limit = datetime.now() - timedelta(hours=36)
    try:
        res = requests.get(feed_url, timeout=20)
        feed = feedparser.parse(res.text)
        for entry in feed.entries:
            if path_keyword in entry.link.lower():
                articles.append({'title': entry.title, 'link': entry.link, 'source': source})
    except: pass
    return articles

def main():
    print(f"Start Media Focus Scraper op {datetime.now().strftime('%d-%m %H:%M')}")
    all_found = []

    # Verzamelen van alle bronnen
    all_found.extend(get_nrc())
    all_found.extend(get_volkskrant_via_alerts())
    all_found.extend(get_trouw_via_alerts()) # Nieuwe bron toegevoegd
    all_found.extend(get_rss_articles("Parool", "https://www.parool.nl/rss.xml", "/han-lips/"))
    all_found.extend(get_rss_articles("Telegraaf", "https://www.telegraaf.nl/entertainment/rss", "/entertainment/media/"))

    # Uniek maken op basis van link
    seen_links = set()
    final_list = []
    for art in all_found:
        if art['link'] not in seen_links:
            final_list.append(art)
            seen_links.add(art['link'])

    if final_list:
        final_list.sort(key=lambda x: x['source'])
        
        body = "<h2>⭐ Media Focus: Update (Laatste 36 uur)</h2>"
        for art in final_list:
            archive_url = f"https://archive.is/{art['link']}"
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br>"
            body += f"<a href='{art['link']}'>Origineel</a> | <a href='{archive_url}'>🔓 Archive.is</a></p>"
        
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"📺 Media Focus {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print(f"Klaar! {len(final_list)} artikelen gevonden. Status email: {response.status_code}")
    else:
        print("Geen nieuwe artikelen gevonden.")

if __name__ == "__main__":
    main()
