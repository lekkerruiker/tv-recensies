import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

# --- CONFIGURATIE ---
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

# We gebruiken headers die exact lijken op een echte Chrome browser op Windows
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'max-age=0',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
}

def scrape_robust(source, url, path_keyword, check_date=False):
    articles = []
    try:
        print(f"Poging tot scannen van {source}...")
        # We voegen een timeout en headers toe om door de muur te komen
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            print(f"Fout: {source} geeft status {response.status_code}")
            return []

        # We zoeken met Regex naar alle links in de ruwe tekst die het keyword bevatten
        # Dit werkt vaak beter bij DPG sites die veel Javascript gebruiken
        raw_links = re.findall(r'href="([^"]*?' + re.escape(path_keyword) + r'[^"]*?)"', response.text)
        
        # Ook de titels proberen te vangen die vaak in de buurt van de link staan
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for link in set(raw_links): # 'set' om dubbelen direct te lozen
            # Maak link absoluut
            if link.startswith('/'):
                base = "https://www.volkskrant.nl" if "volkskrant" in source.lower() else \
                       "https://www.parool.nl" if "parool" in source.lower() else \
                       "https://www.nrc.nl" if "nrc" in source.lower() else \
                       "https://www.telegraaf.nl"
                full_url = base + link
            else:
                full_url = link

            # Filter op datum (voor NRC)
            if check_date:
                today = datetime.now().strftime('%Y/%m/%d')
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
                if today not in full_url and yesterday not in full_url:
                    continue

            # Titel fix: we proberen de titel uit de URL te halen als BeautifulSoup hem niet vindt
            # van: /televisie/dit-is-een-titel~b123/ -> "Dit is een titel"
            url_part = full_url.split('/')[-2] if full_url.endswith('/') else full_url.split('/')[-1]
            clean_title = url_part.split('~')[0].replace('-', ' ').capitalize()
            
            # Alleen toevoegen als het een echt artikel lijkt (bevat meestal ~b bij DPG of -a bij NRC)
            if any(x in full_url for x in ['~b', '-a', '/nieuws/']):
                articles.append({'title': clean_title, 'link': full_url, 'source': source})
                
    except Exception as e:
        print(f"Kritieke fout bij {source}: {e}")
    return articles

def main():
    all_found = []
    
    # Voer de opdrachten exact uit volgens jouw specificaties
    all_found.extend(scrape_robust("Volkskrant", "https://www.volkskrant.nl/televisie/", "/televisie/"))
    all_found.extend(scrape_robust("Parool", "https://www.parool.nl/han-lips/", "/han-lips/"))
    all_found.extend(scrape_robust("NRC", "https://www.nrc.nl/onderwerp/zap/", "/nieuws/", check_date=True))
    all_found.extend(scrape_robust("Telegraaf", "https://www.telegraaf.nl/entertainment/media/", "/entertainment/media/"))

    # Dubbelen verwijderen op basis van URL
    final_list = []
    seen = set()
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
        print(f"Mail verzonden met {len(final_list)} artikelen.")
    else:
        print("Niets gevonden. Controleer of de kranten hun sites hebben aangepast.")

if __name__ == "__main__":
    main()
