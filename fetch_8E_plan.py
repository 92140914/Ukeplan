import requests
import pdfplumber
from datetime import datetime
import json

PDF_URL = "https://www.bergen.kommune.no/api/rest/filer/V69584027"
OUTPUT_FILE = "ukeplan_8E.json"

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag"]

NØKKELORD = [
    "lekse","lekser","oppgave","innlevering","frist","lese","leseboken","leseloggen",
    "øve","øving","presentasjon","fremføring","prøve","prøver","kapittelprøve",
    "gloseprøve","gloseprøver","quiz","test","vurdering","eksamen","utviklingssamtale",
    "samtale","classroom","digitaleoppgaver","video","film","arbeid i boken","arbeid i heftet",
    "oppgavesett","sidene","repetisjon","forberedelse","fag","tema","prosjekt","arbeid videre",
    "innleveringsfrist","se i classroom","avspasering","planleggingsdag"
]

# Hent PDF
r = requests.get(PDF_URL)
pdf_path = "temp.pdf"
with open(pdf_path, "wb") as f:
    f.write(r.content)

resultat = []

with pdfplumber.open(pdf_path) as pdf:
    linjer = []
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            linjer.extend(text.splitlines())

current_day = None

for line in linjer:
    line_clean = line.strip()
    if not line_clean:
        continue

    # Sjekk om linjen inneholder ukedag
    for dag in UKEDAGER:
        if dag in line_clean:
            current_day = dag
            break

    # Sjekk om linjen inneholder nøkkelord
    if any(ord i line_clean.lower() for ord in NØKKELORD):
        resultat.append({
            "tekst": line_clean,
            "ukedag": current_day,
            "dato": datetime.utcnow().strftime("%Y-%m-%d")
        })

# Lagre JSON
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(resultat, f, ensure_ascii=False, indent=2)

print(f"Ferdig, lagret {len(resultat)} oppgaver i {OUTPUT_FILE}")
