import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

# Instellingen (worden uit GitHub Secrets gehaald)
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT", 587)
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# Bronnen om te scrapen
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
            
            # Zoek naar linkjes (simpele logica voor de vibe)
            links = soup.find_all('a', href=True)
            count = 0
            for link in links:
                href = link['href']
                text = link.get_text().strip()
                
                # Filter op relevante termen (bijv. 'recensie')
                if 'recensie' in text.lower() or 'tv' in text.lower():
                    if not href.startswith('http'):
                        base = url.split('.nl')[0] + '.nl'
                        href = base + href
                    
                    # Maak de archive link
                    archive_link = f"https://archive.is/{href}"
                    results.append(f"<b>{name}</b>: {text}<br><a href='{archive_link}'>Lees via Archive.is</a><br><br>")
                    count += 1
                if count >= 3: break # Max 3 per krant voor overzicht
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        print("Geen recensies gevonden vandaag.")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"TV Recensies van {datetime.now().strftime('%d-%m-%Y')}"

    msg.attach(MIMEText(f"<html><body><h1>Dagelijkse TV-Updates</h1>{content}</body></html>", 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
            print("Mail succesvol verstuurd!")
    except Exception as e:
        print(f"Mail-fout: {e}")

if __name__ == "__main__":
    reviews = get_reviews()
    send_mail(reviews)
