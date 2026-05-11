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

# Gewenste volgorde voor de e-mail
SOURCE_ORDER = ["Volkskrant", "NRC", "Trouw", "Parool", "Telegraaf"]

# Google Alert RSS feeds
VK_FEEDS = [
    "https://www.google.nl/alerts/feeds/04781440717054478383/4321423776390191439", 
    "https://www.google.nl/alerts/feeds/04781440717054478383/11932785620654586752", 
    "https://www.google.nl/alerts/feeds/04781440717054478383/12023012097167205549"
]
TROUW_FEED = "https://www.google.nl/alerts/feeds/04781440717054478383/9898575911905288324"
PAROOL_FEED = "https://www.google.nl/alerts/feeds/04781440717054478383/15811468516558440453"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

# --- FUNCTIES VOOR DATA OPHALEN ---

def get_nrc():
    articles = []
    try:
        url = "https://www.nrc.nl/onderwerp/zap/"
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        target_dates = [datetime.now().strftime('%Y/%m/%d'), (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')]
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
    articles = []
    try:
        feed = feedparser.parse(TROUW_FEED)
        for entry in feed.entries:
            title = re.sub('<[^<]+?>', '', entry.title).replace(" - Trouw", "").strip()
            raw_link = entry.link
            actual_link = raw_link
            if "url=" in raw_link:
                match = re.search(r'url=(https?://[^&]+)', raw_link)
                if match: actual_link = match.group(1)
            if "trouw.nl/cultuur-media/" in actual_link.lower():
                articles.append({'title': title, 'link': actual_link, 'source': 'Trouw'})
    except: pass
    return articles

def get_parool_via_alerts():
    articles = []
    try:
        feed = feedparser.parse(PAROOL_FEED)
        for entry in feed.entries:
            title = re.sub('<[^<]+?>', '', entry.title).replace(" - Het Parool", "").strip()
            raw_link = entry.link
            actual_link = raw_link
            if "url=" in raw_link:
                match = re.search(r'url=(https?://[^&]+)', raw_link)
                if match: actual_link = match.group(1)
            if "parool.nl/han-lips/" in actual_link.lower():
                articles.append({'title': title, 'link': actual_link, 'source': 'Parool'})
    except: pass
    return articles

def get_rss_articles(source, feed_url, path_keyword):
    articles = []
    try:
        res = requests.get(feed_url, timeout=20)
        feed = feedparser.parse(res.text)
        for entry in feed.entries:
            if path_keyword in entry.link.lower():
                articles.append({'title': entry.title, 'link': entry.link, 'source': source})
    except: pass
    return articles

# --- MAIN LOGIC ---

def main():
    print(f"Start Media Focus Scraper op {datetime.now().strftime('%d-%m %H:%M')}")
    all_found = []

    # Verzamelen
    all_found.extend(get_volkskrant_via_alerts())
    all_found.extend(get_nrc())
    all_found.extend(get_trouw_via_alerts())
    all_found.extend(get_parool_via_alerts())
    all_found.extend(get_rss_articles("Telegraaf", "https://www.telegraaf.nl/entertainment/rss", "/entertainment/media/"))

    # Uniek maken
    seen_links = set()
    final_list = []
    for art in all_found:
        if art['link'] not in seen_links:
            final_list.append(art)
            seen_links.add(art['link'])

    if final_list:
        # --- SORTEREN OP JOUW VOLGORDE ---
        # We maken een dictionary van de volgorde: {"Volkskrant": 0, "NRC": 1, ...}
        order_map = {name: i for i, name in enumerate(SOURCE_ORDER)}
        # Sorteer op basis van de index in SOURCE_ORDER. Onbekende bronnen komen onderaan (99).
        final_list.sort(key=lambda x: order_map.get(x['source'], 99))
        
        # --- EMAIL BODY BOUWEN ---
        body = "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
        body += "<h2 style='color: #333;'>⭐ Media Focus Update</h2>"
        body += f"<p style='color: #666;'>Gevonden artikelen in de laatste 36 uur ({datetime.now().strftime('%d-%m')})</p>"
        body += "<hr style='border: 0; border-top: 1px solid #eee;'>"

        current_source = ""
        for art in final_list:
            # Voeg een kopje toe als de bron verandert
            if art['source'] != current_source:
                current_source = art['source']
                body += f"<h3 style='background-color: #f8f9fa; padding: 5px 10px; border-left: 4px solid #333; margin-top: 25px;'>{current_source}</h3>"
            
            archive_url = f"https://archive.is/{art['link']}"
            body += f"<div style='margin-bottom: 15px; padding-left: 10px;'>"
            body += f"<div style='font-weight: bold; font-size: 16px; margin-bottom: 5px;'>{art['title']}</div>"
            body += f"<a href='{art['link']}' style='color: #007bff; text-decoration: none;'>Origineel</a> | "
            body += f"<a href='{archive_url}' style='color: #28a745; text-decoration: none;'>🔓 Archive.is</a>"
            body += "</div>"
        
        body += "</div>"

        # Verzenden via Resend
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"📺 Media Focus {datetime.now().strftime('%d-%m')}", 
                "html": body
            })
        print(f"Klaar! {len(final_list)} artikelen verzonden. Status: {response.status_code}")
    else:
        print("Geen nieuwe artikelen gevonden.")

if __name__ == "__main__":
    main()
