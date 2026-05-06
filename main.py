import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'nl-NL,nl;q=0.9',
    'Cookie': 'consentUUID=true; p_user_consent=true; distil_muid=true;',
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
    except:
        pass
    return articles

def get_volkskrant():
    """Volkskrant: Playwright headless browser scrape van /archief/, pak alle /televisie/ links."""
    articles = []
    seen_urls = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                locale='nl-NL',
            )
            page = context.new_page()

            print("Playwright: navigeer naar volkskrant.nl/archief/ ...")
            page.goto("https://www.volkskrant.nl/archief/", wait_until="domcontentloaded", timeout=30000)

            # Wacht tot er links op de pagina staan
            page.wait_for_selector("a[href]", timeout=15000)

            # Haal alle links op
            links = page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(el => ({ href: el.href, text: el.innerText.trim() }))"
            )

            print(f"  Totaal links gevonden op pagina: {len(links)}")

            for item in links:
                href = item.get('href', '')
                title = item.get('text', '').strip()

                # Alleen televisie-artikelen
                if 'volkskrant.nl/televisie/' not in href:
                    continue

                # Geen duplicaten
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Titel te kort? Sla over
                if len(title) < 15:
                    continue

                articles.append({'title': title, 'link': href, 'source': 'Volkskrant'})
                print(f"  ✓ {title[:70]}")

            browser.close()

    except Exception as e:
        print(f"  ❌ Playwright fout: {e}")

    print(f"Volkskrant totaal: {len(articles)} artikelen\n")
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
    except:
        pass
    return articles

def main():
    print(f"\n{'='*60}")
    print(f"📺 MEDIA FOCUS SCRAPER")
    print(f"📅 {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    print(f"{'='*60}\n")

    all_found = []

    print("Scraping NRC...")
    all_found.extend(get_nrc())
    print(f"NRC: {len([a for a in all_found if a['source'] == 'NRC'])} artikelen\n")

    print("Scraping Volkskrant (Playwright)...")
    all_found.extend(get_volkskrant())

    print("Scraping Parool (Han Lips)...")
    parool_articles = get_rss_articles("Parool", "https://www.parool.nl/rss.xml", "/han-lips/")
    all_found.extend(parool_articles)
    print(f"Parool: {len(parool_articles)} artikelen\n")

    print("Scraping Telegraaf...")
    telegraaf_articles = get_rss_articles("Telegraaf", "https://www.telegraaf.nl/entertainment/rss", "/entertainment/media/")
    all_found.extend(telegraaf_articles)
    print(f"Telegraaf: {len(telegraaf_articles)} artikelen\n")

    seen = set()
    final_list = []
    for art in all_found:
        if art['link'] not in seen:
            final_list.append(art)
            seen.add(art['link'])

    print(f"{'='*60}")
    print(f"✅ TOTAAL: {len(final_list)} unieke artikelen gevonden")
    print(f"{'='*60}\n")

    if final_list:
        final_list.sort(key=lambda x: x['source'])
        body = "<h2>⭐ Media Focus: Update (Laatste 36 uur)</h2>"
        for art in final_list:
            archive_url = f"https://archive.is/{art['link']}"
            body += f"<p><strong>[{art['source']}]</strong> {art['title']}<br>"
            body += f"<a href='{art['link']}'>Origineel</a> | <a href='{archive_url}'>🔓 Archive.is</a></p>"

        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": EMAIL_FROM,
                    "to": [EMAIL_RECEIVER],
                    "subject": f"📺 Media Focus {datetime.now().strftime('%d-%m')}",
                    "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
                }
            )
            print(f"✅ Email verzonden! Status: {response.status_code}\n")
        except Exception as e:
            print(f"❌ Email fout: {e}\n")
    else:
        print("⚠️  Geen artikelen gevonden - geen email verzonden.\n")

if __name__ == "__main__":
    main()
