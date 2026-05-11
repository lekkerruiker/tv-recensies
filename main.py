import os
import re
import json
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY       = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM    = "onboarding@resend.dev"
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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# HULPFUNCTIES
# ---------------------------------------------------------------------------

def extract_url(raw_link: str) -> str:
    """Haal de echte URL op uit een Google Alert redirect-link."""
    if "url=" in raw_link:
        match = re.search(r"url=(https?://[^&]+)", raw_link)
        if match:
            return match.group(1)
    return raw_link


def load_seen_links() -> set:
    """Laad eerder verstuurde links uit seen_links.json."""
    if not os.path.exists(SEEN_LINKS_FILE):
        return set()
    try:
        with open(SEEN_LINKS_FILE, "r") as f:
            return set(json.load(f).get("links", []))
    except Exception as e:
        print(f"[WAARSCHUWING] Kon {SEEN_LINKS_FILE} niet laden: {e}")
        return set()


def save_seen_links(seen: set) -> None:
    """Sla alle bekende links op in seen_links.json."""
    try:
        with open(SEEN_LINKS_FILE, "w") as f:
            json.dump({"links": list(seen)}, f, indent=2)
    except Exception as e:
        print(f"[WAARSCHUWING] Kon {SEEN_LINKS_FILE} niet opslaan: {e}")


# ---------------------------------------------------------------------------
# SCRAPERS
# ---------------------------------------------------------------------------

def get_via_alerts(source: str, feeds: list, path_keyword: str, title_suffix: str) -> list:
    """Scrape artikelen via Google Alert RSS-feeds."""
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
        except Exception as e:
            print(f"[WAARSCHUWING] {source} feed mislukt ({feed_url}): {e}")
    return articles


def get_nrc() -> list:
    """Scrape NRC-artikelen via de topics-pagina."""
    articles = []
    try:
        res = requests.get("https://www.nrc.nl/onderwerp/zap/", headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, "html.parser")
        target_dates = [
            datetime.now().strftime("%Y/%m/%d"),
            (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d"),
        ]
        for a in soup.find_all("a", href=True):
            link = a["href"]
            if "/nieuws/" in link and any(d in link for d in target_dates):
                full_url = f"https://www.nrc.nl{link}" if link.startswith("/") else link
                title = a.get_text().strip()
                if len(title) > 15:
                    articles.append({"title": title, "link": full_url, "source": "NRC"})
    except Exception as e:
        print(f"[WAARSCHUWING] NRC scraper mislukt: {e}")
    return articles


def get_telegraaf() -> list:
    """Scrape Telegraaf-artikelen via RSS."""
    articles = []
    try:
        res = requests.get("https://www.telegraaf.nl/entertainment/rss", headers=HEADERS, timeout=15)
        feed = feedparser.parse(res.text)
        for entry in feed.entries:
            if "/entertainment/media/" in entry.link.lower():
                articles.append({"title": entry.title, "link": entry.link, "source": "Telegraaf"})
    except Exception as e:
        print(f"[WAARSCHUWING] Telegraaf RSS mislukt: {e}")
    return articles


# ---------------------------------------------------------------------------
# E-MAIL
# ---------------------------------------------------------------------------

def build_email_html(articles: list) -> str:
    """Bouw de HTML-body van de nieuwsbrief op."""
    body = "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
    body += "<h2 style='color: #333;'>⭐ Media Focus Update</h2>"
    body += f"<p style='color: #666;'>Nieuwe artikelen van vandaag ({datetime.now().strftime('%d-%m-%Y')})</p>"
    body += "<hr style='border: 0; border-top: 1px solid #eee;'>"

    current_source = ""
    for art in articles:
        if art["source"] != current_source:
            current_source = art["source"]
            body += (
                f"<h3 style='background-color: #f8f9fa; padding: 5px 10px; "
                f"border-left: 4px solid #333; margin-top: 25px;'>{current_source}</h3>"
            )
        archive_url = f"https://archive.is/{art['link']}"
        body += "<div style='margin-bottom: 15px; padding-left: 10px;'>"
        body += f"<div style='font-weight: bold; font-size: 16px; margin-bottom: 5px;'>{art['title']}</div>"
        body += f"<a href='{art['link']}' style='color: #007bff; text-decoration: none;'>Origineel</a> | "
        body += f"<a href='{archive_url}' style='color: #28a745; text-decoration: none;'>🔓 Archive.is</a>"
        body += "</div>"

    body += "</div>"
    return body


def send_email(articles: list) -> None:
    """Verstuur de nieuwsbrief via Resend."""
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"📺 Media Focus {datetime.now().strftime('%d-%m')}",
            "html": build_email_html(articles),
        },
    )
    if response.status_code == 200:
        print(f"✅ Mail verstuurd met {len(articles)} artikelen.")
    else:
        print(f"❌ Versturen mislukt. Status: {response.status_code} — {response.text}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M')}] Media Focus gestart.")

    if not API_KEY or not EMAIL_RECEIVER:
        raise EnvironmentError("RESEND_API_KEY en EMAIL_RECEIVER zijn vereist als omgevingsvariabelen.")

    # Verzamelen
    all_found = []
    for source, config in SOURCES.items():
        all_found.extend(get_via_alerts(source, **config))
    all_found.extend(get_nrc())
    all_found.extend(get_telegraaf())

    # Dedupliceer binnen deze run op link
    seen_in_run: set = set()
    unique: list = []
    for art in all_found:
        if art["link"] not in seen_in_run:
            unique.append(art)
            seen_in_run.add(art["link"])

    # Filter eerder verstuurde artikelen
    seen_links = load_seen_links()
    new_articles = [a for a in unique if a["link"] not in seen_links]

    if not new_articles:
        print("Geen nieuwe artikelen gevonden. Mail wordt niet verstuurd.")
        return

    # Sorteer op gewenste bronvolgorde
    order_map = {name: i for i, name in enumerate(SOURCE_ORDER)}
    new_articles.sort(key=lambda x: order_map.get(x["source"], 99))

    # Verstuur en sla op
    send_email(new_articles)
    seen_links.update(a["link"] for a in new_articles)
    save_seen_links(seen_links)


if __name__ == "__main__":
    main()
