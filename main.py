import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def scrape_section(source, section_url, required_path, check_date=False):
    """Scant specifieke sectiepagina's op basis van jouw eisen."""
    articles = []
    try:
        response = requests.get(section_url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Maak links absoluut
            if href.startswith('/'):
                domain = "volkskrant.nl" if "volkskrant" in source.lower() else \
                         "parool.nl" if "parool" in source.lower() else \
                         "nrc.nl" if "nrc" in source.lower() else "telegraaf.nl"
                full_url = f"https://www.{domain}{href}"
            else:
                full_url = href

            # Filter 1: Moet de juiste map bevatten (bijv. /televisie/)
            if required_path in full_url:
                # Filter 2: Datum check voor NRC (moet /202X/XX/XX/ bevatten)
                if check_date:
                    today = datetime.now().strftime('%Y/%m/%d')
                    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
                    if today not in full_url and yesterday not in full_url:
                        continue
                
                title = a.get_text().strip()
                if title and len(title) > 15:
                    articles.append({'title': title, 'link': full_url, 'source': source})
    except Exception as e:
        print(f"Fout bij {source}: {e}")
    return articles

def main():
    all_found = []
    
    # Voer de opdrachten per krant uit
    all_found.extend(scrape_section("Volkskrant", "https://www.volkskrant.nl/televisie/", "/televisie/"))
    all_found.extend(scrape_section("Parool", "https://www.parool.nl/han-lips/", "/han-lips/"))
    all_found.extend(scrape_section("NRC", "https://www.nrc.nl/onderwerp/zap/", "/nieuws/", check_date=True))
    all_found.extend(scrape_section("Telegraaf", "https://www.telegraaf.nl/entertainment/media/", "/entertainment/media/"))

    # Uniek maken (verwijder dubbelen)
    seen = set()
    final_list = []
    for art in all_found:
        if art['link'] not in seen:
            final_list.append(art)
            seen.add(art['link'])

    if final_list:
        body = "<h2>⭐ Media Focus: Sectie Scans</h2>"
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
        print(f"Succes: {len(final_list)} artikelen verzonden.")
    else:
        print("Geen nieuwe artikelen gevonden.")

if __name__ == "__main__":
    main()
