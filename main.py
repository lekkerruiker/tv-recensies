import requests
import re
import resend
import os
from datetime import datetime

# Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

resend.api_key = API_KEY

def send_test_mail(body_content):
    try:
        # We proberen de mail te sturen
        params = {
            "from": EMAIL_FROM,
            "to": [EMAIL_RECEIVER],
            "subject": f"Media Scraper Test: {datetime.now().strftime('%H:%M')}",
            "html": f"<html><body>{body_content}</body></html>"
        }
        
        email = resend.Emails.send(params)
        print(f"✅ Resend API geaccepteerd! Email ID: {email['id']}")
        
    except Exception as e:
        print(f"❌ Resend Foutmelding: {str(e)}")

def simple_scrape():
    # Een hele simpele scrape zonder AI om te testen
    headers = {'User-Agent': 'Mozilla/5.0'}
    test_url = "https://www.parool.nl/rss.xml"
    try:
        resp = requests.get(test_url, headers=headers, timeout=10)
        # Zoek gewoon de eerste 3 titels om te zien of we íets hebben
        titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', resp.text)[:5]
        content = "<br>".join(titles)
        return content if content else "Geen titels gevonden in de RSS."
    except Exception as e:
        return f"Scrape fout: {str(e)}"

if __name__ == "__main__":
    print(f"Versturen naar: {EMAIL_RECEIVER}")
    print(f"Versturen vanaf: {EMAIL_FROM}")
    
    blog_content = simple_scrape()
    send_test_mail(f"<h2>Resultaten van de test-run:</h2><p>{blog_content}</p>")
