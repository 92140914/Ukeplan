import pdfplumber
import json
import re
from datetime import datetime

PDF_PATH = "ukeplan.pdf"
OUT_FILE = "ukeplan-8E.json"

KEYWORDS = [
    "lekse","lekser","oppgave","innlevering","frist","lese","leseboken",
    "leseloggen","øve","øving","presentasjon","fremføring","prøve","prøver",
    "kapittelprøve","gloseprøve","gloseprøver","quiz","test","vurdering",
    "eksamen","samtale","classroom","digitaleoppgaver","video","film",
    "arbeid i boken","arbeid i heftet","oppgavesett","sidene","repetisjon",
    "forberedelse","prosjekt","innleveringsfrist","se i classroom"
]

FAG = [
    "norsk","engelsk","matematikk","samfunnsfag","naturfag","kroppsøving",
    "språk","spansk","tysk","fransk","krle","uv","valgfag","k&h","kunst/håndverk","alf"
]

UKEDAGER = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag"]

def er_planleggingsdag(tekst):
    return "planleggingsdag" in tekst.lower()

def gyldig_lekse(tekst):
    t = tekst.lower()
    if len(t.strip()) < 5:
        return False
    if re.search(r"\d{2}\s?\d{2}\s?\d{2}", t):  # telefon
        return False
    if "@" in t or "bergen kommune" in t or "mjølkeråen skole" in t:
        return False
    return any(k in t for k in KEYWORDS)

def finn_fag(tekst):
    t = tekst.lower()
    for fag in FAG:
        if fag in t:
            return fag
    return None

def finn_ukedag(tekst):
    for dag in UKEDAGER:
        if dag.lower() in tekst.lower():
            return dag
    return None

def parse_pdf():
    lekser = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")
            for linje in lines:
                if er_planleggingsdag(linje):
                    continue
                if not gyldig_lekse(linje):
                    continue
                fag = finn_fag(linje)
                ukedag = finn_ukedag(linje)
                lekser.append({
                    "tekst": linje.strip(),
                    "ukedag": ukedag,
                    "fag": fag
                })
    return lekser

def main():
    data = {
        "klasse": "8E",
        "lekser": parse_pdf(),
        "hentet": datetime.utcnow().isoformat() + "Z"
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
