import requests
from bs4 import BeautifulSoup
import resend
import os
import sys
from datetime import datetime

# 1. Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    print("❌ FOUT: Mis gegevens in Secrets.")
    sys.exit(1)

resend.api_key = API_KEY

# RSS Feeds zijn veel toegankelijker voor scripts
FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/kijk-en-luister/rss.xml",
    "Trouw": "https://www.trouw.nl/cultuur-media/rss.xml",
    "Parool": "https://www.parool.nl/columns-opinie/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/entertainment/media/rss"
}

def get_reviews():
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    print("🔍 RSS Sniper gestart...")
    
    for name, url in FEEDS.items():
        try:
            print(f"Lezen van {name} RSS...")
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"⚠️ Kon RSS van {name} niet bereiken (Status {resp.status_code})")
                continue
            
            # RSS is XML, maar BeautifulSoup kan dit prima aan
            soup = BeautifulSoup(resp.content, 'xml')
            items = soup.find_all('item')
            
            found_in_feed = 0
            for item in items:
                title = item.title.get_text()
                link = item.link.get_text()
                
                # Filters per krant (identiek aan je wensen)
                is_match = False
                low_title = title.lower()
                low_link = link.lower()
                
                if name == "NRC" and ("zap" in low_title or "zap" in low_link): is_match = True
                elif name == "Volkskrant" and ("recensie" in low_title or "televisie" in low_link): is_match = True
                elif name == "Trouw" and ("blik van bos" in low_title or "bos" in low_link): is_match = True
                elif name == "Parool" and ("han lips" in low_title or "lips" in low_link): is_match = True
                elif name == "Telegraaf" and ("marcel" in low_title or "marcel" in low_link): is_match = True

                if is_match:
                    archive_link = f"https://archive.is/{link}"
                    results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
                    found_in_feed += 1
                
                if found_in_feed >= 5: break # Pak de laatste 5 per krant
                
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        # Als zelfs de RSS niets geeft, zijn er simpelweg geen nieuwe artikelen met die trefwoorden
        content = "<li>Geen nieuwe recensies gevonden in de RSS-feeds van de afgelopen dagen.</li>"

    html_body = f"""
    <html>
        <body style='font-family: sans-serif; max-width: 600px;'>
            <h2 style='color: #2c3e50;'>📺 TV Recensie Update (RSS)</h2>
            <ul style='list-style: none; padding: 0;'>
                {content}
            </ul>
            <hr>
            <p style='font-size: 0.8em; color: #7f8c8d;'>De achterdeur-methode via RSS.</p>
        </body>
    </html>
    """
    
    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"Media Update: {datetime.now().strftime('%d-%m-%Y')}",
            "html": html_body,
        })
        print("✅ Mail succesvol verzonden!")
    except Exception as e:
        print(f"❌ Resend fout: {e}")

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
