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
    except: pass
    return articles

def get_volkskrant():
    """Volkskrant: Scrape /televisie en /archief voor recensies."""
    articles = []
    seen_urls = set()
    
    urls = [
        "https://www.volkskrant.nl/televisie/",
        "https://www.volkskrant.nl/archief/"
    ]
    
    for page_url in urls:
        try:
            print(f"Scraping {page_url}...")
            res = requests.get(page_url, headers=HEADERS, timeout=20)
            if res.status_code != 200:
                print(f"  Status {res.status_code}")
                continue
            
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Vind alle links op de pagina
            for link_tag in soup.find_all('a', href=True):
                href = link_tag['href']
                
                # Alleen /televisie/ URLs
                if '/televisie/' not in href:
                    continue
                
                # Maak volledige URL
                if href.startswith('http'):
                    full_url = href
                elif href.startswith('/'):
                    full_url = f"https://www.volkskrant.nl{href}"
                else:
                    continue
                
                # Vermijd duplicaten
                if full_url in seen_urls:
                    continue
                
                # Haal titel uit de link text
                title = link_tag.get_text(strip=True)
                
                # Als de link geen goede titel heeft, probeer uit parent elementen
                if len(title) < 15 or title.lower() in ['lees meer', 'meer', 'lees verder', '']:
                    # Zoek in parent voor betere titel
                    parent = link_tag.find_parent(['article', 'div', 'li'])
                    if parent:
                        # Probeer heading te vinden
                        heading = parent.find(['h1', 'h2', 'h3', 'h4'])
                        if heading:
                            title = heading.get_text(strip=True)
                        else:
                            # Probeer span of div met titel class
                            title_elem = parent.find(['span', 'div'], class_=re.compile('title|headline|heading', re.I))
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                
                # Alleen toevoegen als we een fatsoenlijke titel hebben
                if len(title) > 15 and full_url not in seen_urls:
                    articles.append({
                        'title': title,
                        'link': full_url,
                        'source': 'Volkskrant'
                    })
                    seen_urls.add(full_url)
                    print(f"  ✓ Gevonden: {title[:60]}")
                    
        except Exception as e:
            print(f"  ❌ Fout bij {page_url}: {e}")
    
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
    except: pass
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
            response = requests.post("https://api.resend.com/emails", 
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": EMAIL_FROM, 
                    "to": [EMAIL_RECEIVER], 
                    "subject": f"📺 Media Focus {datetime.now().strftime('%d-%m')}", 
                    "html": f"<html><body style='font-family:sans-serif;'>{body}</body></html>"
                })
            print(f"✅ Email verzonden! Status: {response.status_code}\n")
        except Exception as e:
            print(f"❌ Email fout: {e}\n")
    else:
        print("⚠️  Geen artikelen gevonden - geen email verzonden.\n")

if __name__ == "__main__":
    main()
