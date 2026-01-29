import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re

URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"

resp = requests.get(URL)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

current_week = datetime.now().isocalendar()[1]
current_year = datetime.now().year

# Lag stikkord for uken, fleksibelt
week_keywords = [f"{current_week}", f"Uke {current_week}", f"Uke {current_week}-{current_year}", f"Uke {current_week} {current_year}"]

# Lag stikkord for klassen
class_keywords = ["8E", "8-e", "8_e", "8 klasse E", "8.klasse E", "8 E"]

# Finn lenke til ukeplan basert på stikkord
plan_url = None
for a in soup.find_all("a", href=True):
    a_text = a.get_text(strip=True).lower()
    if any(kw.lower() in a_text for kw in week_keywords) and \
       any(kw.lower() in a_text for kw in class_keywords):
        plan_url = a["href"]
        break

if not plan_url:
    raise ValueError("Fant ikke ukeplan for 8E denne uken")

if plan_url.startswith("/"):
    plan_url = "https://www.bergen.kommune.no" + plan_url

plan_resp = requests.get(plan_url)
plan_resp.raise_for_status()
plan_soup = BeautifulSoup(plan_resp.text, "html.parser")

# Hent lekser og prøver med stikkord
keywords = ["lekse", "prøve", "innlevering", "øvelse", "presentasjon"]

entries = []
for li in plan_soup.find_all(["li", "p"]):
    text = li.get_text(" ", strip=True)
    if any(k.lower() in text.lower() for k in keywords):
        date_match = re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]?\d{0,4}\b", text)
        entries.append({
            "tekst": text,
            "dato": date_match.group(0) if date_match else None
        })

with open("ukeplan-8E.json", "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)

print(f"Lagrte {len(entries)} oppføringer i ukeplan-8E.json")
