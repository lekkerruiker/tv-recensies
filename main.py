import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def scrape_section(source, section_url, link_pattern, check_date=False):
    """Scant een specifieke pagina op relevante links."""
    articles = []
    try:
        print(f"Scannen van {source} sectie: {section_url}")
        response = requests.get(section_url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Haal alle links op de pagina op
        for a in soup.find_all('a', href=True):
            href = a['href']
            
            # Maak links absoluut
            if href.startswith('/'):
                domain = "volkskrant.nl" if "volkskrant" in source.lower() else \
                         "parool.nl" if "parool" in source.lower() else \
                         "nrc.nl" if "nrc" in source.lower() else \
                         "telegraaf.nl"
                full_url = f"https://www.{domain}{href}"
            else:
                full_url = href

            # Check of de link voldoet aan jouw specifieke URL-structuur
            if link_pattern in full_url:
                # Bij NRC extra checken op de datum in de URL (24 uur)
                if check_date:
                    today = datetime.now().strftime('%Y/%m/%d')
                    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
                    if today not in full_url and yesterday not in full_url:
                        continue
                
                title = a.get_text().strip()
                # Alleen toevoegen als er een titel is en we de link nog niet hebben
                if title and len(title) > 15:
                    articles.append({'title': title, 'link': full_url, 'source': source})
                    
    except Exception as e:
        print(f"Fout bij {source}: {e}")
    return articles

def main():
    all_found = []
    seen_links = set()

    # 1. Volkskrant: alles op /televisie/
    all_found.extend(scrape_section("Volkskrant", "https://www.volkskrant.nl/televisie/", "/televisie/"))

    # 2. Parool: alles op /han-lips/
    all_found.extend(scrape_section("Parool", "https://www.parool.nl/han-lips/", "/han-lips/"))

    # 3. NRC: scannen op /zap/, maar links filteren op datum in URL
    all_found.extend(scrape_section("NRC", "https://www.nrc.nl/onderwerp/zap/", "/nieuws/", check_date=True))

    # 4. Telegraaf: alles op /entertainment/media/
    all_found.extend(scrape_section("Telegraaf", "https://www.telegraaf.nl/entertainment/media/", "/entertainment/media/"))

    # Uniek maken en e-mail bouwen
    final_list = []
    for art in all_found:
        if art['link'] not in seen_links:
            final_list.append(art)
            seen_links.add(art['link'])

    if final_list:
        body = "<h2>⭐ Media Focus: Sectie Scans (24u)</h2>"
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
        print(f"Mail verzonden met {len(final_list)} artikelen.")
    else:
        print("Geen nieuwe artikelen gevonden op de specifieke pagina's.")

if __name__ == "__main__":
    main()
