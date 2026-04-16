import requests
from bs4 import BeautifulSoup
import resend  # Nieuwe library
import os
from datetime import datetime

# Instellingen uit GitHub Secrets
resend.api_key = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev") # Standaard Resend adres
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

SOURCES = {
    "NRC": "https://www.nrc.nl/rubriek/tv-recensies/",
    "Volkskrant": "https://www.volkskrant.nl/kijk-en-luister",
    "Parool": "https://www.parool.nl/media"
}

def get_reviews():
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, url in SOURCES.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            count = 0
            for link in links:
                href = link['href']
                text = link.get_text().strip()
                if 'recensie' in text.lower() or 'tv' in text.lower():
                    if not href.startswith('http'):
                        base = url.split('.nl')[0] + '.nl'
                        href = base + href
                    archive_link = f"https://archive.is/{href}"
                    results.append(f"<b>{name}</b>: {text}<br><a href='{archive_link}'>Lees via Archive.is</a><br><br>")
                    count += 1
                if count >= 3: break
        except Exception as e:
            print(f"Fout bij {name}: {e}")
    return "".join(results)

def send_mail(content):
    if not content:
        print("Geen recensies gevonden.")
        return

    params = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"TV Recensies - {datetime.now().strftime('%d-%m-%Y')}",
        "html": f"<html><body><h1>Dagelijkse TV-Updates</h1>{content}</body></html>",
    }

    try:
        email = resend.Emails.send(params)
        print(f"Mail verzonden! ID: {email['id']}")
    except Exception as e:
        print(f"Resend fout: {e}")

if __name__ == "__main__":
    reviews = get_reviews()
    send_mail(reviews)
