import pdfplumber
import json
import re
from datetime import datetime

PDF_PATH = "ukeplan.pdf"
OUT = "ukeplan-8E.json"

KEYWORDS = [
    "lekse","lekser","oppgave","innlevering","frist","lese","leseboken",
    "leseloggen","øve","øving","presentasjon","fremføring","prøve","prøver",
    "kapittelprøve","gloseprøve","gloseprøver","quiz","test","vurdering",
    "eksamen","samtale","classroom","digitaleoppgaver","video","film",
    "arbeid i boken","arbeid i heftet","oppgavesett","sidene","repetisjon",
    "forberedelse","prosjekt","innleveringsfrist","se i classroom"
]

UKEDAGER = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag"]

FAG_PER_DAG = {
    "Mandag": ["norsk","matte"],
    "Tirsdag": ["språk","matte"],
    "Onsdag": ["norsk","naturfag"],
    "Torsdag": ["språk","samfunn"],
    "Fredag": ["norsk","matte"]
}

def er_planleggingsdag(tekst):
    return "planleggingsdag" in tekst.lower()

def gyldig_lekse(tekst):
    t = tekst.lower()
    if len(t) < 8:
        return False
    if re.search(r"\d{2}\s?\d{2}\s?\d{2}", t):
        return False
    if "@" in t or "bergen kommune" in t:
        return False
    return any(k in t for k in KEYWORDS)

def finn_fag(tekst, dag):
    t = tekst.lower()
    for fag in FAG_PER_DAG[dag]:
        if fag in t:
            return fag
    return None

def parse_pdf():
    lekser = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            header = table[0]
            for row in table[1:]:
                for i, celle in enumerate(row):
                    if not celle:
                        continue

                    dag = UKEDAGER[i] if i < len(UKEDAGER) else None
                    if not dag:
                        continue

                    if dag == "Fredag" and "språk" in celle.lower():
                        continue

                    if er_planleggingsdag(celle):
                        continue

                    if not gyldig_lekse(celle):
                        continue

                    fag = finn_fag(celle, dag)
                    if not fag:
                        continue

                    lekser.append({
                        "tekst": " ".join(celle.split()),
                        "ukedag": dag,
                        "fag": fag
                    })
    return lekser

def main():
    data = {
        "klasse": "8E",
        "lekser": parse_pdf(),
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
