import os
import requests
import feedparser
from datetime import datetime
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

def get_via_google(source, query):
    """Haalt artikelen op via Google News (omzeilt directe blokkades)."""
    articles = []
    # We zoeken specifiek op de site van de krant via Google
    rss_url = f"https://news.google.com/rss/search?q=site:{source.lower()}.nl+{query}&hl=nl&gl=NL&ceid=NL:nl"
    try:
        resp = requests.get(rss_url, timeout=15)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:10]:
            title = entry.title.split(' - ')[0]
            link = entry.link
            # Check op de Oranjezondag/recensie termen
            if any(x in title.lower() or x in link.lower() for x in ['televisie', 'recensie', 'lips', 'kijkt', 'oranjezondag']):
                articles.append({'title': title, 'link': link, 'source': source})
    except Exception as e:
        print(f"Google News fout voor {source}: {e}")
    return articles

def get_rss_safe(name, url):
    """RSS voor de kranten die meestal wel werken."""
    articles = []
    try:
        resp = requests.get(url, timeout=15)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            t_l = (title + link).lower()
            if any(x in t_l for x in ['televisie', 'tv-recensie', 'han-lips', 'zap:', 'bekeken:']):
                if not any(x in title.lower() for x in ['stikstof', 'boek', 'concert']):
                    articles.append({'title': title, 'link': link, 'source': name})
    except: pass
    return articles

def main():
    all_articles = []
    seen = set()

    # 1. Volkskrant & Parool via Google Bridge (meest kansrijk tegen blokkades)
    all_articles.extend(get_via_google("Volkskrant", "televisie"))
    all_articles.extend(get_via_google("Parool", "Han+Lips"))

    # 2. De rest via RSS
    feeds = {
        "NRC": "https://www.nrc.nl/rss/",
        "Telegraaf": "https://www.telegraaf.nl/rss",
        "Trouw": "https://www.trouw.nl/rss.xml"
    }
    for name, url in feeds.items():
        all_articles.extend(get_rss_safe(name, url))

    # Opschonen
    final_list = []
    for art in all_articles:
        if art['link'] not in seen:
            final_list.append(art)
            seen.add(art['link'])

    # E-mail opbouwen
    if final_list:
        body = "<h2>⭐ Media Selectie</h2>"
        for art in final_list:
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br><a href='{art['link']}'>Lees</a> | <a href='https://archive.is/{art['link']}'>🔓 Archief</a></p>"
    else:
        body = "<p>Vandaag zijn er geen nieuwe recensies gevonden die aan de filters voldoen.</p>"

    # Altijd mailen (zo zie je dat het script werkt)
    requests.post("https://api.resend.com/emails", 
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM, 
            "to": [EMAIL_RECEIVER], 
            "subject": f"Media Focus {datetime.now().strftime('%d-%m')}", 
            "html": f"<html><body>{body}</body></html>"
        })

if __name__ == "__main__":
    main()
