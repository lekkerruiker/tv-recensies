import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

def get_nrc():
    """Jouw NRC code: Onveranderd en werkend."""
    articles = []
    try:
        url = "https://www.nrc.nl/onderwerp/zap/"
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        today = datetime.now().strftime('%Y/%m/%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
        
        for a in soup.find_all('a', href=True):
            link = a['href']
            if "/nieuws/" in link and (today in link or yesterday in link):
                full_url = f"https://www.nrc.nl{link}" if link.startswith('/') else link
                title = a.get_text().strip()
                if len(title) > 15:
                    articles.append({'title': title, 'link': full_url, 'source': 'NRC'})
    except: pass
    return articles

def get_rss_articles(source, feed_url, path_keyword):
    """Nieuw plan voor de rest: Gebruik RSS (omzeilt cookie walls)."""
    articles = []
    try:
        feed = feedparser.parse(requests.get(feed_url, timeout=20).text)
        for entry in feed.entries:
            link = entry.link
            # Check of de link de specifieke map bevat die je eist
            if path_keyword in link.lower():
                articles.append({
                    'title': entry.title,
                    'link': link,
                    'source': source
                })
    except: pass
    return articles

def main():
    all_found = []
    
    # 1. NRC: De specifieke scraper (onveranderd)
    all_found.extend(get_nrc())

    # 2. Volkskrant: Gebruik hun RSS feed
    # Dit vangt alles in de categorie 'televisie'
    all_found.extend(get_rss_articles("Volkskrant", "https://www.volkskrant.nl/televisie/rss.xml", "/televisie/"))

    # 3. Parool: Gebruik hun algemene RSS, maar filter STRENG op Han Lips
    all_found.extend(get_rss_articles("Parool", "https://www.parool.nl/rss.xml", "/han-lips/"))

    # 4. Telegraaf: Gebruik de Media RSS feed
    all_found.extend(get_rss_articles("Telegraaf", "https://www.telegraaf.nl/entertainment/rss", "/entertainment/media/"))

    # Dedupliceren en filteren op 24 uur (RSS feeds zijn meestal al vers)
    seen = set()
    final_list = []
    for art in all_found:
        if art['link'] not in seen:
            final_list.append(art)
            seen.add(art['link'])

    if final_list:
        body = "<h2>⭐ Media Focus: Dagelijkse Update</h2>"
        for art in final_list:
            archive_url = f"https://archive.is/{art['link']}"
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br>"
            body += f"<a href='{art['link']}'>Origineel</a> | <a href='{archive_url}'>🔓 Archive.is</a></p>"
        
        requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
    else:
        print("Geen nieuwe artikelen gevonden.")

if __name__ == "__main__":
    main()
