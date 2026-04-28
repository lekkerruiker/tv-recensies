import os
import requests
import feedparser
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_articles():
    articles = []
    seen_links = set()
    
    # 1. DPG (Volkskrant & Parool) via Google News RSS
    # We zoeken nu breed op de site, en filteren zelf op de URL-structuur
    queries = [
        ("Volkskrant", "site:volkskrant.nl"),
        ("Parool", "site:parool.nl Han Lips")
    ]
    
    for source, q in queries:
        try:
            # We halen de laatste 3 dagen op
            rss_url = f"https://news.google.com/rss/search?q={q}+when:3d&hl=nl&gl=NL&ceid=NL:nl"
            feed = feedparser.parse(requests.get(rss_url, timeout=15).text)
            
            for entry in feed.entries:
                link = entry.link
                title = entry.title.split(' - ')[0]
                l_lower = link.lower()
                t_lower = title.lower()
                
                # DE ENIGE HARDE CRITERIA:
                # Volkskrant: moet /televisie/ in de URL hebben
                # Parool: moet /han-lips/ of /televisie/ in de URL hebben of 'Han Lips' in de titel
                is_match = False
                if source == "Volkskrant" and "/televisie/" in l_lower:
                    is_match = True
                if source == "Parool" and ("/televisie/" in l_lower or "/han-lips/" in l_lower or "han lips" in t_lower):
                    is_match = True
                
                if is_match and link not in seen_links:
                    articles.append({'title': title, 'link': link, 'source': source})
                    seen_links.add(link)
        except: pass

    # 2. Andere kranten (NRC, Telegraaf, Trouw) via hun eigen RSS
    rss_feeds = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }
    
    for source, url in rss_feeds.items():
        try:
            feed = feedparser.parse(requests.get(url, timeout=15).text)
            for entry in feed.entries:
                link = entry.link
                title = entry.title
                l_lower = link.lower()
                t_lower = title.lower()
                
                # Check op de map /televisie/ of specifieke recensie-termen
                # Dit vangt de NRC Koningsdag-recensie omdat die in de map /televisie/ staat
                if "/televisie/" in l_lower or any(x in t_lower for x in ["zap:", "bekeken:", "tv-recensie", "maaike bos"]):
                    if link not in seen_links:
                        articles.append({'title': title, 'link': link, 'source': source})
                        seen_links.add(link)
        except: pass

    return articles

def main():
    all_articles = get_articles()
    
    if all_articles:
        body = "<h2>⭐ Media Focus Selectie</h2>"
        # Sorteer op bron
        for art in sorted(all_articles, key=lambda x: x['source']):
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees artikel</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    else:
        body = "Geen nieuwe media-artikelen gevonden in de secties /televisie/ van de afgelopen 3 dagen."

    # Altijd mailen ter controle
    requests.post("https://api.resend.com/emails", 
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM, 
            "to": [EMAIL_RECEIVER], 
            "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", 
            "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
        })

if __name__ == "__main__":
    main()
