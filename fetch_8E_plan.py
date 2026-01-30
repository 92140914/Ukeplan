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
PLANLEGGINGS_ORD = ["planleggingsdag", "elevfri", "avspasering"]
FAGLISTE = ["Norsk", "Matematikk", "Engelsk", "Spansk", "Tysk", "Fransk",
            "Naturfag", "Samfunnsfag", "KRLE", "Kroppsøving", "K&H", "ALF", "Valgfag"]

OPPGAVE_REGEX = r"(s\.?\s*\d+[-–]?\d*|oppgave\s*\d+|side\s*\d+)"
PRØVE_REGEX = r"(prøve|test)"

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
    current_fag = None
    buffer_tekst = []
    buffer_side = []
    buffer_is_prove = False

    def lagre_buffer():
        nonlocal buffer_tekst, buffer_side, buffer_is_prove, current_day, current_fag
        if not buffer_tekst:
            return
        tekst_samlet = " ".join(buffer_tekst)
        side_samlet = buffer_side[:2] if buffer_side else None
        oppgave = {
            "tekst": tekst_samlet,
            "dato": datetime.utcnow().strftime("%Y-%m-%d"),
            "ukedag": current_day,
            "side_eller_oppgave": side_samlet,
            "fag": current_fag
        }
        if buffer_is_prove:
            prover.append(oppgave)
        else:
            lekser.append(oppgave)
        buffer_tekst = []
        buffer_side = []
        buffer_is_prove = False

    for line in linjer:
        # ignorerer irrelevante linjer
        if any(x.lower() in line.lower() for x in ["arbeidsplan", "53 03 57 30", "mjølkeråen skole", "pals", "info:", "emne:", "time tid"]):
            continue
        if any(p.lower() in line.lower() for p in PLANLEGGINGS_ORD):
            current_fag = None
            current_day = None
            buffer_tekst.append(line)  # lagre planleggingsdag som lekse
            lagre_buffer()
            continue

        # oppdater ukedag
        for dag in UKEDAGER:
            if line.startswith(dag):
                lagre_buffer()
                current_day = dag
                line = line[len(dag):].strip()
                break

        # oppdater fag
        fag = None
        for f in FAGLISTE:
            if line.startswith(f):
                lagre_buffer()
                fag = f
                line = line[len(f):].strip()
                break
        if fag:
            current_fag = fag

        # oppgaveekstraksjon
        oppgaver = re.findall(OPPGAVE_REGEX, line)
        if oppgaver:
            buffer_side.extend(oppgaver)

        # sjekk om prøve
        is_prove = bool(re.search(PRØVE_REGEX, line, re.IGNORECASE))

        # multiline AI logikk: hvis linje er tom eller ny fag/ny dag, lagre buffer
        if line == "":
            lagre_buffer()
            continue

        # samler tekst
        buffer_tekst.append(line)
        if is_prove:
            buffer_is_prove = True

    # lagre siste
    lagre_buffer()

    # filtrer tomme fag/ukedag
    lekser = [l for l in lekser if l["tekst"].strip()]
    prover = [p for p in prover if p["tekst"].strip()]

    # maks 2 oppgavenr per lekse
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
