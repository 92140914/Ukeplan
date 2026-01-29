import requests
import json
import re
from datetime import datetime, timedelta
import fitz  # PyMuPDF

KLASSE = "8E"
BASE_URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUTPUT_FILE = f"ukeplan-{KLASSE}.json"

UKEDAGER_NO = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag"]
UKEDAGER_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# Mapping fag
FAG_LISTE = [
    "Matematikk", "Norsk", "Kroppsøving", "Naturfag", "Samfunnsfag", "KRLE",
    "Engelsk", "Engelsk fordypning", "Spansk", "Fransk", "Tysk", "K&H", "ALF", "Valgfag"
]

# Hent nyeste ukeplan
def hent_ukeplan_pdf():
    r = requests.get(f"{BASE_URL}/uke-5-2026")  # dynamisk uke kan settes her
    r.raise_for_status()
    # Finn 8E-fil
    fil_match = re.search(r'href="(.*?{}.*?)"'.format(KLASSE), r.text)
    if not fil_match:
        raise RuntimeError(f"Fant ingen fil for klasse {KLASSE}")
    fil_url = fil_match.group(1)
    if not fil_url.startswith("http"):
        fil_url = "https://www.bergen.kommune.no" + fil_url
    pdf_data = requests.get(fil_url).content
    with open(f"{KLASSE}.pdf", "wb") as f:
        f.write(pdf_data)
    return f"{KLASSE}.pdf", fil_url

# Konverter PDF til tekst
def pdf_to_text(pdf_file):
    doc = fitz.open(pdf_file)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# Finn dato fra ukedag og uke
def ukedag_til_dato(ukedag, uke, år=None):
    if not år:
        år = datetime.now().year
    første_januar = datetime(år, 1, 4)  # ISO uke 1 alltid inneholder 4. jan
    start_uke = første_januar - timedelta(days=første_januar.isoweekday() - 1)
    dag_index = UKEDAGER_NO.index(ukedag)
    dato = start_uke + timedelta(weeks=uke-1, days=dag_index)
    return dato.strftime("%Y-%m-%d")

# Parse lekser og prøver
def parse_lekser_prover(text, uke):
    lekser = []
    prover = []
    lines = text.split("\n")
    current_day = None
    for line in lines:
        line = line.strip()
        # Finn dag
        for dag in UKEDAGER_NO + UKEDAGER_EN:
            if re.match(rf'^{dag}\b', line, re.I):
                current_day = dag
                break
        if not current_day:
            continue
        # Finn fag i linjen
        for fag in sorted(FAG_LISTE, key=lambda x: -len(x)):
            if re.search(rf'\b{fag}\b', line, re.I):
                side_match = re.search(r's[.:]?\s*(\d+(-\d+)?)', line, re.I)
                side_oppgave = f"side {side_match.group(1)}" if side_match else None
                entry = {
                    "tekst": line,
                    "dato": ukedag_til_dato(current_day, uke),
                    "ukedag": current_day,
                    "side_eller_oppgave": side_oppgave,
                    "fag": fag.lower()
                }
                # Heuristikk for prøver
                if re.search(r'\bprøve|test\b', line, re.I):
                    prover.append(entry)
                else:
                    lekser.append(entry)
                break
    return lekser, prover

def main():
    pdf_file, fil_url = hent_ukeplan_pdf()
    text = pdf_to_text(pdf_file)
    uke = 5  # dynamisk kan settes etter nåværende uke
    lekser, prover = parse_lekser_prover(text, uke)
    data = {
        "uke": uke,
        "klasse": KLASSE,
        "kilde": fil_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Lekser og prøver hentet. Lagret i {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
