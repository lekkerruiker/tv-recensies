import os
import re
import json
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURATIE ---
API_KEY         = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER  = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM      = "onboarding@resend.dev"
SEEN_LINKS_FILE = "seen_links.json"

SOURCE_ORDER = ["Volkskrant", "Volkskrant Kijkkunde", "NRC", "Trouw", "Parool", "Telegraaf"]

SOURCES = {
    "Volkskrant": {
        "feeds": [
            "https://www.google.nl/alerts/feeds/04781440717054478383/4321423776390191439",
            "https://www.google.nl/alerts/feeds/04781440717054478383/12023012097167205549",
        ],
        "path_keywords": ["volkskrant.nl/televisie/", "volkskrant.nl/nieuwe-series/", "volkskrant.nl/kijkverder/"],
        "title_suffix": " - de Volkskrant",
    },
    "Volkskrant Kijkkunde": {
        "feeds": ["https://www.google.nl/alerts/feeds/04781440717054478383/11932785620654586752"],
        "path_keywords": ["volkskrant.nl"],
        "title_suffix": " - de Volkskrant",
    },
    "Trouw": {
        "feeds": ["https://www.google.nl/alerts/feeds/04781440717054478383/9898575911905288324"],
        "path_keywords": ["trouw.nl/cultuur-media/"],
        "title_suffix": " - Trouw",
    },
    "Parool": {
        "feeds": ["https://www.google.nl/alerts/feeds/04781440717054478383/15811468516558440453"],
        "path_keywords": ["parool.nl/han-lips/"],
        "title_suffix": " - Het Parool",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# ---------------------------------------------------------------------------
# HULPFUNCTIES
# ---------------------------------------------------------------------------

def extract_url(raw_link: str) -> str:
    if "url=" in raw_link:
        match = re.search(r"url=(https?://[^&]+)", raw_link)
        if match:
            return match.group(1)
    return raw_link

def load_seen_links() -> set:
    if not os.path.exists(SEEN_LINKS_FILE):
        return set()
    try:
        with open(SEEN_LINKS_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("links", []) if isinstance(data, dict) else data)
    except Exception as e:
        print(f"[WAARSCHUWING] Kon {SEEN_LINKS_FILE} niet laden: {e}")
        return set()

def save_seen_links(seen: set) -> None:
    limited = list(seen)[-500:]
    try:
        with open(SEEN_LINKS_FILE, "w") as f:
            json.dump({"links": limited}, f, indent=2)
    except Exception as e:
        print(f"[WAARSCHUWING] Kon {SEEN_LINKS_FILE} niet opslaan: {e}")

# ---------------------------------------------------------------------------
# SCRAPERS
# ---------------------------------------------------------------------------

def get_via_alerts(source: str, feeds: list, title_suffix: str, path_keywords: list) -> list:
    articles = []
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(res.text)
            for entry in feed.entries:
                title = re.sub("<[^<]+?>", "", entry.title).replace(title_suffix, "").strip()
                link = extract_url(entry.link)
                if any(kw in link.lower() for kw in path_keywords):
                    articles.append({"title": title, "link": link, "source": source})
        except Exception as e:
            print(f"[FOUT] {source} feed mislukt: {e}")
    return articles

def get_nrc() -> list:
    articles = []
    try:
        res = requests.get("https://www.nrc.nl/onderwerp/zap/", headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "/nieuws/" in a["href"]:
                link = f"https://www.nrc.nl{a['href']}" if a["href"].startswith("/") else a["href"]
                title = a.get_text().strip()
                if len(title) > 15:
                    articles.append({"title": title, "link": link, "source": "NRC"})
    except Exception as e:
        print(f"[FOUT] NRC scraper mislukt: {e}")
    return articles

def get_telegraaf() -> list:
    articles = []
    try:
        res = requests.get("https://www.telegraaf.nl/entertainment/rss", headers=HEADERS, timeout=15)
        feed = feedparser.parse(res.text)
        for entry in feed.entries:
            if "/entertainment/media/" in entry.link.lower():
                title = entry.title.split("|")[0].strip()
                articles.append({"title": title, "link": entry.link, "source": "Telegraaf"})
    except Exception as e:
        print(f"[FOUT] Telegraaf RSS mislukt: {e}")
    return articles

# ---------------------------------------------------------------------------
# E-MAIL & MAIN
# ---------------------------------------------------------------------------

def build_email_html(articles: list) -> str:
    body = "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
    body += "<h2>⭐ Media Focus Update</h2>"
    body
