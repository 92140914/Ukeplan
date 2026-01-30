import requests
import pdfplumber
import re
import json
from datetime import datetime, timedelta
from io import BytesIO

PDF_URL = "https://www.bergen.kommune.no/api/rest/filer/V69584027"
KLASSE = "8E"
UKE = 5

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag"]

FAG = [
    "Norsk", "Matematikk", "Engelsk", "Engelsk fordypning",
    "Samfunnsfag", "Naturfag", "KRLE",
    "Kroppsøving", "Kunst", "Kunst og håndverk", "K&H",
    "Spansk", "Fransk", "Tysk", "ALF", "Arbeidslivsfag",
    "Valgfag"
]

PROVE_ORD = ["prøve", "test"]
LEKSE_ORD = [
    "les", "gjør", "jobb", "øve", "presentasjon",
    "presentation", "video", "se", "fremføring",
    "classroom"
]

SIDE_REGEX = re.compile(r"s\.?\s*(\d+)(?:\s*[–-]\s*(\d+))?", re.I)

def uke_start_dato(year, week):
    jan4 = datetime(year, 1, 4)
    start = jan4 - timedelta(days=jan4.weekday())
    return start + timedelta(weeks=week - 1)

def last_pdf_text():
    r = requests.get(PDF_URL, timeout=30)
    r.raise_for_status()
    text = []
    with pdfplumber.open(BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text.append(t)
    return "\n".join(text)

def clean_lines(text):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("ARBEIDSPLAN"):
            continue
        lines.append(line)
    return lines

def is_fag(line):
    for f in FAG:
        if line.lower().startswith(f.lower()):
            return f
    return None

def extract_side(text):
    m = SIDE_REGEX.search(text)
    if not m:
        return None
    if m.group(2):
        return f"side {m.group(1)}-{m.group(2)}"
    return f"side {m.group(1)}"

def parse_dagseksjon(lines):
    seksjoner = {}
    current_day = None

    for line in lines:
        if line in UKEDAGER:
            current_day = line
            seksjoner[current_day] = []
            continue
        if current_day:
            seksjoner[current_day].append(line)

    return seksjoner

def parse_lekser(seksjoner, uke_start):
    lekser = []
    prover = []

    for dag, lines in seksjoner.items():
        dato = uke_start + timedelta(days=UKEDAGER.index(dag))
        current_fag = None
        buffer = []

        def flush():
            if not buffer or not current_fag:
                return
            tekst = " ".join(buffer).strip()
            side = extract_side(tekst)

            entry = {
                "tekst": tekst,
                "dato": dato.strftime("%Y-%m-%d"),
                "ukedag": dag,
                "side_eller_oppgave": side,
                "fag": current_fag.lower()
            }

            low = tekst.lower()
            if any(w in low for w in PROVE_ORD):
                prover.append(entry)
            else:
                lekser.append(entry)

        for line in lines:
            fag = is_fag(line)
            if fag:
                flush()
                current_fag = fag
                buffer = []
                rest = line[len(fag):].strip()
                if rest:
                    buffer.append(rest)
                continue

            buffer.append(line)

        flush()

    return lekser, prover

def main():
    year = datetime.utcnow().year
    uke_start = uke_start_dato(year, UKE)

    raw_text = last_pdf_text()
    lines = clean_lines(raw_text)

    seksjoner = parse_dagseksjon(lines)
    lekser, prover = parse_lekser(seksjoner, uke_start)

    data = {
        "uke": UKE,
        "klasse": KLASSE,
        "kilde": PDF_URL,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open("ukeplan-8E.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
