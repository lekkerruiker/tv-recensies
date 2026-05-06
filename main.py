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

# We gebruiken een zeer uitgebreide header om niet als bot herkend te worden
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

def get_nrc():
    """NRC: Onveranderd."""
    articles = []
    try:
        url = "https://www.nrc.nl/onderwerp/zap/"
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        target_dates = [
            datetime.now().strftime('%Y/%m/%d'),
            (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d'),
            (datetime.now() - timedelta(days=2)).strftime('%Y/%m/%d')
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

def get_volkskrant():
    """Volkskrant: Scant de archiefpagina met Regex op alles wat naar /televisie/ wijst."""
    articles = []
    url = "https://www.volkskrant.nl/archief/"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=25)
        # We zoeken in de RUWE tekst (res.text) naar patronen die lijken op: /televisie/...~b.../
        # Dit vindt links ook in de Javascript/JSON blokken van Next.js
        found_links = re.findall(r'\"(/televisie/[^\"\s]+~b[^\"\s]+/?)\"', res.text)
        
        # Soms zijn links zonder de ~b ID, die pakken we ook mee
        found_links += re.findall(r'href=\"(/televisie/[^\"\s]+)\"', res.text)

        for link in set(found_links):
            # Schoon de link op (verwijder eventuele quotes of backslashes van JSON)
            clean_link = link.replace('\\', '')
            full_url = f"https://www.volkskrant.nl{clean_link}" if clean_link.startswith('/') else clean_link
            
            # Titel uit de URL halen (betrouwbaarder dan HTML tags bij Next.js)
            # Voorbeeld: /televisie/hier-staat-de-titel~b12345/
            parts = clean_link.split('/')
            slug = parts[-2] if clean_link.endswith('/') else parts[-1]
            title = slug.split('~')[0].replace('-', ' ').capitalize()
            
            if len(title) > 10:
                articles.append({'title': title, 'link': full_url, 'source': 'Volkskrant'})
    except Exception as e:
        print(f"Volkskrant scan fout: {e}")
        
    return articles

def get_rss_articles(source, feed_url, path_keyword):
    """Parool & Telegraaf: Onveranderd."""
    articles = []
    limit = datetime.now() - timedelta(hours=36)
    try:
        feed = feedparser.parse(requests.get(feed_url, timeout=20).text)
        for entry in feed.entries:
            if path_keyword in entry.link.lower():
                try:
                    pub_date = datetime(*entry.published_parsed[:6])
                    if pub_date > limit:
                        articles.append({'title': entry.title, 'link': entry.link, 'source': source})
                except:
                    articles.append({'title': entry.title, 'link': entry.link, 'source': source})
    except: pass
    return articles

def main():
    all_found = []
    
    all_found.extend(get_nrc())
    all_found.extend(get_volkskrant())
    all_found.extend(get_rss_articles("Parool", "https://www.parool.nl/rss.xml", "/han-lips/"))
    all_found.extend(get_rss_articles("Telegraaf", "https://www.telegraaf.nl/entertainment/rss", "/entertainment/media/"))

    seen = set()
    final_list = []
    for art in all_found:
        if art['link'] not in seen:
            final_list.append(art)
            seen.add(art['link'])

    if final_list:
        final_list.sort(key=lambda x: x['source'])
        body = "<h2>⭐ Media Focus: Update (Laatste 36 uur)</h2>"
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
