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
    if "url=" in raw_link:
        match = re.search(r"url=(https?://[^&]+)", raw_link)
        if match:
            return match.group(1)
    return raw_link


def load_seen_links() -> set:
    if not os.path.exists(SEEN_LINKS_FILE):
        print("[GEHEUGEN] seen_links.json niet gevonden — eerste run, alles is nieuw.")
        return set()
    try:
        with open(SEEN_LINKS_FILE, "r") as f:
            data = json.load(f)
        links = data.get("links", []) if isinstance(data, dict) else data
        print(f"[GEHEUGEN] {len(links)} eerder verstuurde links geladen.")
        return set(links)
    except Exception as e:
        print(f"[WAARSCHUWING] Kon {SEEN_LINKS_FILE} niet laden: {e}")
        return set()


def save_seen_links(seen: set) -> None:
    limited = list(seen)[-500:]
    try:
        with open(SEEN_LINKS_FILE, "w") as f:
            json.dump({"links": limited}, f, indent=2)
        print(f"[GEHEUGEN] {len(limited)} links opgeslagen in {SEEN_LINKS_FILE}.")
    except Exception as e:
        print(f"[WAARSCHUWING] Kon {SEEN_LINKS_FILE} niet opslaan: {e}")


# ---------------------------------------------------------------------------
# SCRAPERS
# ---------------------------------------------------------------------------

def get_via_alerts(source: str, feeds: list, path_keyword: str, title_suffix: str) -> list:
    articles = []
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(res.text)
            raw_count = len(feed.entries)
            matched = 0
            for entry in feed.entries:
                title = re.sub("<[^<]+?>", "", entry.title).replace(title_suffix, "").strip()
                link = extract_url(entry.link)
                if path_keyword in link.lower():
                    articles.append({"title": title, "link": link, "source": source})
                    matched += 1
            print(f"[{source}] Feed ...{feed_url[-30:]} → {raw_count} entries, {matched} matchen op '{path_keyword}'")
        except Exception as e:
            print(f"[FOUT] {source} feed mislukt (...{feed_url[-30:]}): {e}")
    return articles


def get_nrc() -> list:
    articles = []
    try:
        res = requests.get("https://www.nrc.nl/onderwerp/zap/", headers=HEADERS, timeout=20)
        print(f"[NRC] Pagina opgehaald (status {res.status_code}, {len(res.text)} bytes)")
        soup = BeautifulSoup(res.text, "html.parser")
        all_links = soup.find_all("a", href=True)
        nieuws_links = [a for a in all_links if "/nieuws/" in a["href"]]
        print(f"[NRC] {len(all_links)} links gevonden, {len(nieuws_links)} met /nieuws/")
        for a in nieuws_links:
            link = a["href"]
            full_url = f"https://www.nrc.nl{link}" if link.startswith("/") else link
            title = a.get_text().strip()
            if len(title) > 15:
                articles.append({"title": title, "link": full_url, "source": "NRC"})
        print(f"[NRC] {len(articles)} artikelen na titelfilter (>15 tekens)")
    except Exception as e:
        print(f"[FOUT] NRC scraper mislukt: {e}")
    return articles


def get_telegraaf() -> list:
    articles = []
    try:
        res = requests.get("https://www.telegraaf.nl/entertainment/rss", headers=HEADERS, timeout=15)
        feed = feedparser.parse(res.text)
        raw_count = len(feed.entries)
        matched = 0
        for entry in feed.entries:
            if "/entertainment/media/" in entry.link.lower():
                title = entry.title.split("|")[0].strip()
                articles.append({"title": title, "link": entry.link, "source": "Telegraaf"})
                matched += 1
        print(f"[Telegraaf] {raw_count} entries in feed, {matched} matchen op /entertainment/media/")
    except Exception as e:
        print(f"[FOUT] Telegraaf RSS mislukt: {e}")
    return articles


# ---------------------------------------------------------------------------
# E-MAIL
# ---------------------------------------------------------------------------

def build_email_html(articles: list) -> str:
    body = "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
    body += "<h2>⭐ Media Focus Update</h2>"
    body += f"<p>Nieuwe artikelen gevonden op {datetime.now().strftime('%d-%m-%Y')}:</p>"

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
        body += f"<div style='font-weight: bold;'>{art['title']}</div>"
        body += f"<a href='{art['link']}'>Origineel</a> | <a href='{archive_url}'>🔓 Archive.is</a>"
        body += "</div>"

    body += "</div>"
    return body


def send_email(articles: list) -> bool:
    res = requests.post(
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
    print(f"[RESEND] Status: {res.status_code} | Response: {res.text}")
    return res.status_code in [200, 201]


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*50}")
    print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M')}] Media Focus gestart.")
    print(f"{'='*50}")

    if not API_KEY or not EMAIL_RECEIVER:
        print("[FOUT] Omgevingsvariabelen RESEND_API_KEY en/of EMAIL_RECEIVER ontbreken.")
        return

    # --- Verzamelen ---
    all_found = []
    for source, config in SOURCES.items():
        all_found.extend(get_via_alerts(source, **config))
    all_found.extend(get_nrc())
    all_found.extend(get_telegraaf())
    print(f"\n[TOTAAL] {len(all_found)} artikelen gevonden voor deduplicatie.")

    # --- Dedupliceer binnen deze run ---
    seen_in_run: set = set()
    unique_this_run = []
    for art in all_found:
        if art["link"] not in seen_in_run:
            unique_this_run.append(art)
            seen_in_run.add(art["link"])
    print(f"[TOTAAL] {len(unique_this_run)} uniek na interne deduplicatie.")

    # --- Filter eerder verstuurde artikelen ---
    history = load_seen_links()
    new_articles = [a for a in unique_this_run if a["link"] not in history]
    print(f"[TOTAAL] {len(new_articles)} nieuw na historiefilter.")

    if not new_articles:
        print("\n[RESULTAAT] Geen nieuwe artikelen — mail wordt niet verstuurd.")
        return

    # --- Sorteren ---
    order_map = {name: i for i, name in enumerate(SOURCE_ORDER)}
    new_articles.sort(key=lambda x: order_map.get(x["source"], 99))

    # --- Versturen ---
    print(f"\n[MAIL] Versturen van {len(new_articles)} artikelen naar {EMAIL_RECEIVER}...")
    if send_email(new_articles):
        print(f"[RESULTAAT] ✅ Mail verstuurd met {len(new_articles)} artikelen.")
        history.update(a["link"] for a in new_articles)
        save_seen_links(history)
    else:
        print("[RESULTAAT] ❌ Versturen mislukt — seen_links NIET bijgewerkt.")


if __name__ == "__main__":
    main()
