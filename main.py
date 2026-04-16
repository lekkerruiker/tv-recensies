import requests
import re
import resend
import os
import sys
from datetime import datetime

# 1. Instellingen
API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

if not API_KEY or not EMAIL_RECEIVER:
    sys.exit(1)

resend.api_key = API_KEY

FEEDS = {
    "NRC": "https://www.nrc.nl/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def get_reviews():
    results = []
    KEYWORDS = ['lips', 'zap', 'bos', 'peereboom', 'marcel', 'recensie', 'kijkt', 'serie', 'televisie', 'tv-']
    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            # We behandelen de hele feed als platte tekst om blokkades te omzeilen
            content = resp.text

            # We hakken de tekst op in individuele <item> blokken
            items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
            
            for item in items:
                # We vissen de titel en link eruit met Regex
                title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                link_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                
                # Fallback voor link via <guid> als <link> leeg is
                if not link_match:
                    link_match = re.search(r'<guid.*?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</guid>', item, re.DOTALL)

                if title_match and link_match:
                    title = title_match.group(1).strip()
                    link = link_match.group(1).strip()
                    
                    # Opschonen van eventuele HTML restanten in de titel
                    title = re.sub('<[^<]+?>', '', title)

                    combined_text = (title + " " + link).lower()
                    if any(k in combined_text for k in KEYWORDS):
                        if not any(link in r for r in results):
                            archive_link = f"https://archive.is/{link}"
                            results.append(f"<li><strong>[{name}]</strong> {title}<br><a href='{archive_link}'>🔓 Lees via Archive.is</a></li><br>")
        
        except Exception as e:
            print(f"Fout bij {name}: {e}")
            
    return "".join(results)

def send_mail(content):
    if not content:
        content = "<li>Geen nieuwe recensies gevonden vandaag.</li>"

    html_body = f"""
    <html>
        <body style='font-family: Arial, sans-serif; line-height: 1.6;'>
            <h2 style='color: #2c3e50;'>📺 TV & Media Update</h2>
            <ul style='list-style: none; padding: 0;'>
                {content}
            </ul>
        </body>
    </html>
    """
    
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [EMAIL_RECEIVER],
        "subject": f"Media Update: {datetime.now().strftime('%d-%m')}",
        "html": html_body,
    })

if __name__ == "__main__":
    content = get_reviews()
    send_mail(content)
