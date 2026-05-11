import os
import re
import json
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY         = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER  = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM      = "onboarding@resend.dev"
SEEN_LINKS_FILE = "seen_links.json"

SOURCE_ORDER = ["Volkskrant", "NRC", "Trouw", "Parool", "Telegraaf"]

SOURCES = {
    "Volkskrant": {
        "feeds": [
            "https://www.google.nl/alerts/feeds/04781440717054478383/4321423776390191439",
            "https://www.google.nl/alerts/feeds/04781440717054478383/11932785620654586752",
            "https://www.google.nl/alerts/feeds/04781440717054478383/12023012097167205549",
        ],
        "path_keyword": "volkskrant.nl/televisie/",
        "title_suffix": " - de Volkskrant",
    },
    "Trouw": {
        "feeds": ["https://www.google.nl/alerts/feeds/04781440717054478383/9898575911905288324"],
        "path_keyword": "trouw.nl/cultuur-media/",
        "title_suffix": " - Trouw",
    },
    "Parool": {
        "feeds": ["https://www.google.nl/alerts/feeds/04781440717054478383/15811468516558440453"],
        "path_keyword": "parool.nl/han-lips/",
        "title_suffix": " - Het Parool",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# --- HULPFUNCTIES ---

def extract_url(raw_link: str) -> str:
    if "url=" in raw_link:
        match = re.search(r"url=(https?://[^&]+)", raw_link)
        if match: return match.group(1)
    return raw_link

def load_seen_links() -> set:
    if not os.path.exists(SEEN_LINKS_FILE):
        return set()
    try:
        with open(SEEN_LINKS_FILE, "r") as f:
            data = json.load(f)
            # Ondersteuning voor zowel oude lijst als nieuwe dict structuur
            links = data.get("links", []) if isinstance(data, dict) else data
            return set(links)
    except:
        return set()

def save_seen_links(seen: set) -> None:
    # We bewaren alleen de laatste 500 links om de file klein te houden voor GitHub
    limit_links = list(seen)[-500:] 
    with open(SEEN_LINKS_FILE, "w") as f:
        json.dump({"links": limit_links}, f, indent=2)

# --- SCRAPERS ---

def get_via_alerts(source: str, feeds: list, path_keyword: str, title_suffix: str) -> list:
    articles = []
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(res.text)
            for entry in feed.entries:
                title = re.sub("<[^<]+?>", "", entry.title).replace(title_suffix, "").strip()
                link = extract_url(entry.link)
                if path_keyword in link.lower():
                    articles.append({"title": title, "link": link, "source": source})
        except: pass
    return articles

def get_nrc() -> list:
    """NRC: We halen de datum-check weg omdat we nu een geheugen (JSON) hebben."""
    articles = []
    try:
        res = requests.get("https://www.nrc.nl/onderwerp/zap/", headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, "html.parser")
        for a in soup.find_all("a", href=True):
            link = a["href"]
            # We checken alleen of het een nieuwsartikel is
            if "/nieuws/" in link:
                full_url = f"https://www.nrc.nl{link}" if link.startswith("/") else link
                title = a.get_text().strip()
                if len(title) > 15:
                    articles.append({"title": title, "link": full_url, "source": "NRC"})
    except: pass
    return articles

def get_telegraaf() -> list:
    articles = []
    try:
        res = requests.get("https://www.telegraaf.nl/entertainment/rss", headers=HEADERS, timeout=15)
        feed = feedparser.parse(res.text)
        for entry in feed.entries:
            if "/entertainment/media/" in entry.link.lower():
                # Telegraaf titels zijn soms erg lang, we halen de bronvermelding weg
                title = entry.title.split('|')[0].strip()
                articles.append({"title": title, "link": entry.link, "source": "Telegraaf"})
    except: pass
    return articles

# --- MAIN ---

def main():
    print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M')}] Media Focus gestart.")
    
    if not API_KEY or not EMAIL_RECEIVER:
        print("FOUT: Omgevingsvariabelen ontbreken.")
        return

    all_found = []
    for source, config in SOURCES.items():
        all_found.extend(get_via_alerts(source, **config))
    all_found.extend(get_nrc())
    all_found.extend(get_telegraaf())

    # 1. Uniek maken binnen deze run
    seen_in_run = set()
    unique_this_run = []
    for art in all_found:
        if art["link"] not in seen_in_run:
            unique_this_run.append(art)
            seen_in_run.add(art["link"])

    # 2. Filteren tegen historisch archief
    history = load_seen_links()
    new_articles = [a for a in unique_this_run if a["link"] not in history]

    if not new_articles:
        print("Geen nieuwe artikelen gevonden.")
        return

    # 3. Sorteren
    order_map = {name: i for i, name in enumerate(SOURCE_ORDER)}
    new_articles.sort(key=lambda x: order_map.get(x["source"], 99))

    # 4. Email bouwen en versturen
    body = "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
    body += "<h2>⭐ Media Focus Update</h2>"
    body += f"<p>Nieuwe artikelen gevonden op {datetime.now().strftime('%d-%m-%Y')}:</p>"
    
    current_source = ""
    for art in new_articles:
        if art["source"] != current_source:
            current_source = art["source"]
            body += f"<h3 style='background-color: #f8f9fa; padding: 5px 10px; border-left: 4px solid #333; margin-top: 25px;'>{current_source}</h3>"
        
        archive_url = f"https://archive.is/{art['link']}"
        body += f"<div style='margin-bottom: 15px; padding-left: 10px;'>"
        body += f"<div style='font-weight: bold;'>{art['title']}</div>"
        body += f"<a href='{art['link']}'>Origineel</a> | <a href='{archive_url}'>🔓 Archive.is</a>"
        body += "</div>"
    body += "</div>"

    res = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"📺 Media Focus {datetime.now().strftime('%d-%m')}",
            "html": body
        }
    )

    if res.status_code in [200, 201]:
        print(f"✅ Succes! {len(new_articles)} nieuwe artikelen verstuurd.")
        # Update geschiedenis
        for a in new_articles:
            history.add(a["link"])
        save_seen_links(history)
    else:
        print(f"❌ Email fout: {res.text}")

if __name__ == "__main__":
    main()
