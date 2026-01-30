import requests
import pdfplumber
import re
import json
from datetime import datetime

# === KONFIGURASJON ===
KLASSE = "8E"
UKE = 5
PDF_URL = "https://www.bergen.kommune.no/api/rest/filer/V69584027"
OUTPUT_FILE = f"ukeplan-{KLASSE}-AI.json"

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag"]

# Nøkkelord for å filtrere lekser/prøver/oppgaver
NØKKELORD = [
    "lekse","lekser","oppgave","innlevering","frist","lese","leseboken","leseloggen",
    "øve","øving","presentasjon","fremføring","prøve","prøver","kapittelprøve",
    "gloseprøve","gloseprøver","quiz","test","vurdering","eksamen","utviklingssamtale",
    "samtale","classroom","digitaleoppgaver","video","film","arbeid i boken","arbeid i heftet",
    "oppgavesett","sidene","repetisjon","forberedelse","fag","tema","prosjekt","arbeid videre",
    "innleveringsfrist","se i classroom","avspasering","planleggingsdag"
]

# Regex for oppgavenummer/side
OPPGAVE_REGEX = r"(s\.?\s*\d+[-–]?\d*|oppgave\s*\d+|side\s*\d+)"

# === HENT PDF ===
def hent_pdf(url):
    r = requests.get(url)
    r.raise_for_status()
    path = f"{KLASSE}.pdf"
    with open(path, "wb") as f:
        f.write(r.content)
    return path

# === AI-PROSESSERING ===
def ai_prosessering(pdf_path):
    lekser = []
    prover = []

    with pdfplumber.open(pdf_path) as pdf:
        tekst = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

    linjer = [line.strip() for line in tekst.splitlines() if line.strip()]

    current_day = None
    buffer_tekst = []
    buffer_side = []
    buffer_is_prove = False

    def lagre_buffer():
        nonlocal buffer_tekst, buffer_side, buffer_is_prove, current_day
        if not buffer_tekst:
            return
        tekst_samlet = " ".join(buffer_tekst)
        side_samlet = buffer_side[:2] if buffer_side else None
        oppgave = {
            "tekst": tekst_samlet,
            "dato": datetime.utcnow().strftime("%Y-%m-%d"),
            "ukedag": current_day,
            "side_eller_oppgave": side_samlet
        }
        if buffer_is_prove:
            prover.append(oppgave)
        else:
            lekser.append(oppgave)
        buffer_tekst.clear()
        buffer_side.clear()
        buffer_is_prove = False

    for line in linjer:
        # oppdater ukedag
        for dag in UKEDAGER:
            if line.startswith(dag):
                lagre_buffer()
                current_day = dag
                line = line[len(dag):].strip()
                break

        # sjekk om linjen inneholder nøkkelord
        if any(nk in line.lower() for nk in NØKKELORD):
            # hent oppgavenummer/side
            oppgaver = re.findall(OPPGAVE_REGEX, line)
            if oppgaver:
                buffer_side.extend(oppgaver)
            # sjekk om det er prøve
            buffer_is_prove = bool(re.search(r"prøve|test", line, re.IGNORECASE))
            buffer_tekst.append(line)
        else:
            # linje uten nøkkelord lagres ikke
            continue

        # lagre buffer hvis linjen er tom
        if line == "":
            lagre_buffer()

    # lagre siste
    lagre_buffer()

    # maks 2 oppgavenr per lekse/prøve
    for l in lekser:
        if l["side_eller_oppgave"]:
            l["side_eller_oppgave"] = l["side_eller_oppgave"][:2]
    for p in prover:
        if p["side_eller_oppgave"]:
            p["side_eller_oppgave"] = p["side_eller_oppgave"][:2]

    return lekser, prover

# === MAIN ===
def main():
    pdf_path = hent_pdf(PDF_URL)
    lekser, prover = ai_prosessering(pdf_path)

    data = {
        "uke": UKE,
        "klasse": KLASSE,
        "kilde": PDF_URL,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"AI ukeplan ferdig lagret i {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
