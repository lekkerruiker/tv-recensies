import os
import requests
import sys
from datetime import datetime

def run_diagnostic():
    print("--- START DIAGNOSE ---")
    
    # 1. Check de variabelen (zonder de hele key te tonen voor veiligheid)
    api_key = os.getenv("RESEND_API_KEY")
    to_email = os.getenv("EMAIL_RECEIVER")
    from_email = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

    print(f"Tijdstip: {datetime.now()}")
    print(f"Ontvanger ingesteld: {'JA' if to_email else 'NEE'}")
    print(f"API-sleutel ingesteld: {'JA' if api_key else 'NEE'}")
    
    if not api_key or not to_email:
        print("❌ CRITIEKE FOUT: Variabelen ontbreken. Controleer je GitHub Secrets en YML env sectie.")
        return

    # 2. Handmatige API aanroep via requests (om de library te omzeilen)
    print(f"Poging om mail te sturen naar {to_email} via Resend API...")
    
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": "Systeemtest Scraper",
        "html": f"<strong>Test geslaagd!</strong> De scraper werkt op {datetime.now()}"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Ruwe Respons: {response.text}")
        
        if response.status_code == 200 or response.status_code == 201:
            print("✅ HET IS GELUKT: De Resend server heeft de mail geaccepteerd.")
        else:
            print("❌ SERVER WEIGERING: Resend zag de aanvraag maar weigerde deze.")
            
    except Exception as e:
        print(f"❌ VERBINDINGSFOUT: Kon niet praten met Resend. Fout: {e}")

if __name__ == "__main__":
    run_diagnostic()
    print("--- EINDE DIAGNOSE ---")
