import os
import requests
import re
from datetime import datetime
import json

# --- CONFIGURATIE ---
# Zorg dat deze in GitHub Secrets staan
API_KEY = os.getenv("RESEND_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_FROM = "onboarding@resend.dev"

FEEDS = {
    "NRC": "https://www.nrc.nl/onderwerp/zap/rss/",
    "Volkskrant": "https://www.volkskrant.nl/rss.xml",
    "Trouw": "https://www.trouw.nl/rss.xml",
    "Parool": "https://www.parool.nl/rss.xml",
    "Telegraaf": "https://www.telegraaf.nl/rss"
}

def clean_text(text):
    if not text: return ""
    # Verwijder CDATA, HTML tags en overtollige witruimte
    text = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+?>', '', text)
    return " ".join(text.split())

def get_ai_sorted_list(articles):
    if not GEMINI_KEY or not articles:
        return articles
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    input_data = [{"id": i, "title": a['title'], "source": a['source'], "snippet": a['snippet'][:100]} for i, a in enumerate(articles)]
    
    prompt = (
        "Je bent een media-assistent voor een TV-professional. Sorteer deze artikelen. "
        "PRIORITEIT 1: TV-recensies (Maaike Bos, Han Lips, NRC Zap, Volkskrant recensies). "
        "PRIORITEIT 2: Nieuws over NPO, RTL, SBS, talkshows, kijkcijfers en Tina Nijkamp. "
        "VERWIJDER: Alles wat niet direct met TV/Media te maken heeft. "
        "OUTPUT: Geef ENKEL de JSON lijst met ID-nummers terug, bijv: [3, 0, 2]"
        f"Lijst: {json.dumps(input_data)}"
    )
    
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        res_json = resp.json()
        raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
        # Zoek de blokhaken in de tekst van Gemini
        ids = json.loads(re.search(r'\[.*\]', raw_text).group())
        return [articles[i] for i in ids if i < len(articles)]
    except Exception as e:
        print(f"AI Sortering mislukt: {e}")
        return articles

def run_scraper():
    all_found = []
    seen_links = set()
    
    # Namen van recensenten en VIP termen
    CRITICS = ['lips', 'fortuin', 'peereboom', 'maaike bos', 'beukers', 'stokmans', 'wels', 'nijkamp', 'angela de jong']

    # Belangrijk: NRC blokkeert als er geen User-Agent is
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for name, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"Kon {name} niet laden (Status {resp.status_code})")
                continue
                
            items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            
            for item in items:
                t_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                l_match = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
                
                if t_match and l_match:
                    title = clean_text(t_match.group(1))
                    link = l_match.group(1).strip()
                    
                    if link in seen_links: continue

                    desc_match = re.search(r'<(?:description|content:encoded|summary)>(.*?)</(?:description|content:encoded|summary)>', item, re.DOTALL)
                    snippet = clean_text(desc_match.group(1)) if desc_match else ""
                    full_lower = (title + " " + snippet + " " + link).lower()

                    keep = False
                    
                    # --- FILTER LOGICA ---
                    if name == "NRC":
                        # Alles uit de specifieke Zap-feed is relevant
                        keep = True
                    
                    elif name == "Trouw":
                        if "maaike bos" in full_lower:
                            keep = True
                    
                    elif name == "Parool" and "han-lips" in link.lower():
                        keep = True
                        
                    elif name == "Volkskrant" and "televisie" in link.lower():
                        keep = True
                    
                    elif name == "Telegraaf" and "entertainment/media" in link.lower():
                        keep = True
                    
                    else:
                        # Algemene media check voor overige items
                        media_keywords = ['talkshow', 'npo', 'rtl', 'sbs', 'kijkcijfer', 'televisie', 'omroep']
                        if any(word in title.lower() for word in media_keywords) or any(c in title.lower() for c in CRITICS):
                            keep = True

                    # --- HARD BLOCK VOOR RUIS (behalve voor NRC/VIPs) ---
                    if any(bad in title.lower() for bad in ['gaza', 'soedan', 'oekraïne', 'pkn']):
                        if name != "NRC" and not any(vip in title.lower() for vip in ['lips', 'maaike bos']):
                            keep = False

                    if keep:
                        all_found.append({"title": title, "link": link, "source": name, "snippet": snippet})
                        seen_links.add(link)
        except Exception as e:
            print(f"Fout bij bron {name}: {e}")
            continue
    
    return get_ai_sorted_list(all_found)

if __name__ == "__main__":
    try:
        articles = run_scraper()
        
        if articles:
            results_html = ""
            for i, art in enumerate(articles, 1):
                # Maak archive link
                archive_link = f"https://archive.is/{art['link']}"
                # Top 5 krijgt een oranje accent
                border_color = "#e67e22" if i <= 5 else "#bdc3c7"
                
                results_html += f"""
                <li style='margin-bottom: 25px; list-style: none; border-left: 4px solid {border_color}; padding-left: 15px;'>
                    <strong style='font-size: 16px; color: #2c3e50;'>[{art['source']}] {art['title']}</strong><br>
                    <p style='margin: 6px 0; color: #555; font-size: 14px;'>{art['snippet'][:180]}...</p>
                    <a href='{archive_link}' style='color: #3498db; text-decoration: none; font-size: 12px; font-weight: bold;'>🔓 Lees via Archive.is</a>
                </li>"""

            email_body = f"""
            <html>
                <body style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;'>
                    <h2 style='color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px;'>📺 Media Focus: {datetime.now().strftime('%d-%m-%Y')}</h2>
                    <ul style='padding: 0;'>
                        {results_html}
                    </ul>
                    <hr style='border: 0; border-top: 1px solid #ecf0f1; margin-top: 30px;'>
                    <p style='font-size: 11px; color: #95a5a6;'>Geselecteerd door AI & Scraper. Dagelijks om 08:00.</p>
                </body>
            </html>
            """

            response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": EMAIL_FROM,
                    "to": [EMAIL_RECEIVER],
                    "subject": f"Media Focus: {datetime.now().strftime('%d-%m')}",
                    "html": email_body
                }
            )
            print(f"Mail verzonden! Status: {response.status_code}")
        else:
            print("Geen relevante artikelen gevonden om te verzenden.")
            
    except Exception as e:
        print(f"Kritieke fout in main: {e}")
