import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

def get_nrc():
    """NRC: Onveranderd (3-daagse check)."""
    articles = []
    try:
        url = "https://www.nrc.nl/onderwerp/zap/"
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        today = datetime.now().strftime('%Y/%m/%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
        eergisteren = (datetime.now() - timedelta(days=2)).strftime('%Y/%m/%d')
        target_dates = [today, yesterday, eergisteren]
        
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
    """Volkskrant: Terug naar de werkende basis-scraper van de sectiepagina."""
    articles = []
    # We scannen de directe landingspagina, dit werkte in de eerste versies het beste
    url = "https://www.volkskrant.nl/televisie/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Zoek naar de kenmerkende Volkskrant artikel-URL structuur
            if "/televisie/" in href and "~b" in href:
                full_url = f"https://www.volkskrant.nl{href}" if href.startswith('/') else href
                title = a.get_text().strip()
                
                # Als er geen tekst is, halen we de titel uit de URL slug
                if not title or len(title) < 10:
                    slug = href.split('/')[-2] if href.endswith('/') else href.split('/')[-1]
                    title = slug.split('~')[0].replace('-', ' ').capitalize()
                
                if len(title) > 10:
                    articles.append({'title': title, 'link': full_url, 'source': 'Volkskrant'})
    except: pass
    return articles

def get_rss_articles(source, feed_url, path_keyword):
    """Parool & Telegraaf: Onveranderd (36 uur check)."""
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
                    # Als de feed geen datum heeft, laten we hem door (veiligheidsmarge)
                    articles.append({'title': entry.title, 'link': entry.link, 'source': source})
    except: pass
    return articles

def main():
    all_found = []
    
    # 1. NRC
    all_found.extend(get_nrc())
    # 2. Volkskrant (Herstelde methode)
    all_found.extend(get_volkskrant())
    # 3. Parool
    all_found.extend(get_rss_articles("Parool", "https://www.parool.nl/rss.xml", "/han-lips/"))
    # 4. Telegraaf
    all_found.extend(get_rss_articles("Telegraaf", "https://www.telegraaf.nl/entertainment/rss", "/entertainment/media/"))

    # Uniek maken op basis van URL
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
        print("Geen artikelen gevonden.")

if __name__ == "__main__":
    main()
