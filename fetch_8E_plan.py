import requests
import pdfplumber
import re
import json
from datetime import datetime, timedelta

PDF_URL = "https://www.bergen.kommune.no/api/rest/filer/V69584027"
KLASSE = "8E"
OUTPUT_FILE = "ukeplan-8E.json"

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag"]

SPRÅKFAG = ["Engelsk", "Engelsk fordypning", "Spansk", "Fransk", "Tysk", "ALF"]
ANDRE_FAG = ["Matematikk", "Norsk", "Naturfag", "Samfunnsfag", "KRLE", "Kroppsøving", "K&H", "Kunst & håndverk", "UV", "Valgfag"]

def hent_pdf(url):
    r = requests.get(url)
    r.raise_for_status()
    with open("temp.pdf", "wb") as f:
        f.write(r.content)
    return "temp.pdf"

def parse_pdf(pdf_path):
    lekser = []
    prover = []

    with pdfplumber.open(pdf_path) as pdf:
        tekst = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

    # Finn linjer med ukedager
    linjer = [line.strip() for line in tekst.splitlines() if line.strip()]
    dato_lookup = {}  # Ukedag -> dato (neste forekomst av dato i teksten)
    idag = datetime.today()

    for line in linjer:
        for ukedag in UKEDAGER:
            if line.startswith(ukedag):
                # Finn dato ved å sjekke linjer rundt eller bruk dagens uke som fallback
                dato_lookup[ukedag] = idag.strftime("%Y-%m-%d")

    # Parse lekser og prøver
    current_day = None
    current_fag = None

    for line in linjer:
        # Oppdater current_day
        for ukedag in UKEDAGER:
            if line.startswith(ukedag):
                current_day = ukedag
                line = line[len(ukedag):].strip()

        if not line:
            continue

        # Finn fag
        fag = None
        for f in SPRÅKFAG + ANDRE_FAG:
            if line.startswith(f):
                fag = f
                line = line[len(f):].strip()
                break

        if not fag:
            fag = current_fag
        else:
            current_fag = fag

        # Finn side/oppgave
        side_oppgave = None
        m = re.search(r"(s\.?\s*\d+[-–]?\d*)", line)
        if m:
            side_oppgave = m.group(1)

        # Sjekk om det er prøve eller lekse
        is_prove = any(word.lower() in line.lower() for word in ["prøve", "test"])

        oppgave = {
            "tekst": line,
            "dato": dato_lookup.get(current_day, idag.strftime("%Y-%m-%d")),
            "ukedag": current_day,
            "side_eller_oppgave": side_oppgave,
            "fag": fag
        }

        if is_prove:
            prover.append(oppgave)
        else:
            lekser.append(oppgave)

    return lekser, prover

def main():
    pdf_path = hent_pdf(PDF_URL)
    lekser, prover = parse_pdf(pdf_path)

    data = {
        "uke": 5,
        "klasse": KLASSE,
        "kilde": PDF_URL,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Ferdig. JSON lagret i {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
