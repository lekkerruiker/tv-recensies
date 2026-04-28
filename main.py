import os
import requests
import feedparser
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_specific_media_articles():
    articles = []
    seen_links = set()
    limit = datetime.now() - timedelta(hours=48)
    
    # 1. DPG via Google News (Volkskrant & Parool)
    queries = [("Parool", "Han+Lips"), ("Volkskrant", "televisie+recensie")]
    for source, q in queries:
        try:
            rss_url = f"https://news.google.com/rss/search?q=site:{source.lower()}.nl+{q}+when:2d&hl=nl&gl=NL&ceid=NL:nl"
            feed = feedparser.parse(requests.get(rss_url, timeout=15).text)
            for entry in feed.entries:
                # Veilige datumcheck
                try:
                    pub_date = datetime(*entry.published_parsed[:6])
                    if pub_date < limit: continue
                except: pass # Bij ontbrekende datum gewoon doorgaan
                
                title = entry.title.split(' - ')[0]
                link = entry.link
                t_l = (title + link).lower()
                
                is_media = any(x in t_l for x in ['han-lips', 'televisie', 'recensie', 'maaike-bos', 'kijkcijfers'])
                is_noise = any(x in t_l for x in ['koningsdag', 'marathon', 'voetbal', 'ajax', 'overleden', 'brand', 'steekpartij'])
                
                if is_media and not is_noise and link not in seen_links:
                    articles.append({'title': title, 'link': link, 'source': source})
                    seen_links.add(link)
        except: pass

    # 2. Overige via RSS (NRC, Telegraaf, Trouw)
    rss_feeds = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }
    for source, url in rss_feeds.items():
        try:
            feed = feedparser.parse(requests.get(url, timeout=15).text)
            for entry in feed.entries:
                title = entry.get('title', '')
                link = entry.get('link', '')
                t_l = (title + link).lower()
                
                if any(x in t_l for x in ['tv-recensie', 'maaike-bos', 'zap:', 'bekeken:']) and link not in seen_links:
                    articles.append({'title': title, 'link': link, 'source': source})
                    seen_links.add(link)
        except: pass

    return articles

def main():
    try:
        all_articles = get_specific_media_articles()
        
        if all_articles:
            body = "<h2>⭐ Media Focus: De Selectie</h2>"
            for art in sorted(all_articles, key=lambda x: x['source']):
                body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
        else:
            body = "<p>Geen nieuwe media-artikelen gevonden in de afgelopen 48 uur.</p>"

        # Verzend de mail
        res = requests.post("https://api.resend.com/emails", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "from": EMAIL_FROM, 
                "to": [EMAIL_RECEIVER], 
                "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", 
                "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
            })
        print(f"Status: {res.status_code}")
    except Exception as e:
        print(f"Kritieke fout in main: {e}")

if __name__ == "__main__":
    main()
