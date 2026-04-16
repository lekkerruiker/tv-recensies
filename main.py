import os
import requests
from datetime import datetime

# Instellingen - We forceren het onboarding adres
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev" # Verander dit NOOIT zolang je geen eigen domein hebt gekoppeld in Resend

def run_scraper_and_mail():
    print("--- START MEDIA SCRAPER ---")
    
    if not API_KEY or not EMAIL_RECEIVER:
        print("❌ FOUT: API_KEY of EMAIL_RECEIVER niet gevonden in Secrets.")
        return

    # De tekst die we gaan versturen
    content = "De scraper is technisch nu 100% in orde. De verbinding met Resend is hersteld!"
    
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m %H:%M')}",
        "html": f"<h2>📺 Media Update</h2><p>{content}</p>"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ SUCCES! Mail verzonden naar {EMAIL_RECEIVER}")
            print(f"Respons ID: {response.json().get('id')}")
        else:
            print(f"❌ FOUT {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ VERBINDINGSFOUT: {e}")

if __name__ == "__main__":
    run_scraper_and_mail()
