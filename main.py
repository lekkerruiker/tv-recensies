import os
import resend
from datetime import datetime

# Haal variabelen op
api_key = os.getenv("RESEND_API_KEY")
to_email = os.getenv("EMAIL_RECEIVER")
from_email = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

resend.api_key = api_key

def debug_mail():
    print(f"--- DEBUG INFO ---")
    print(f"Versturen naar: {to_email}")
    print(f"Versturen vanaf: {from_email}")
    print(f"API Key aanwezig: {'Ja' if api_key else 'Nee'}")
    
    try:
        print("Poging tot versturen...")
        r = resend.Emails.send({
            "from": from_email,
            "to": to_email,
            "subject": "DEBUG: Test van Media Scraper",
            "html": f"<p>Test run op {datetime.now()}</p>"
        })
        print(f"✅ API Respons ontvangen: {r}")
        print("Check nu je inbox (en spam)!")
    except Exception as e:
        print(f"❌ Resend gaf een foutmelding: {str(e)}")

if __name__ == "__main__":
    debug_mail()
