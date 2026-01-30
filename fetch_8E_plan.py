import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import re

URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
KLASSE = "8E"
UKE = "5"

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
    if len(t) < 8:
        return False
    if re.search(r"\d{2}\s?\d{2}\s?\d{2}", t):
        return False
    if "@" in t or "bergen kommune" in t:
        return False
    return any(k in t for k in KEYWORDS)

def finn_fag(tekst):
    t = tekst.lower()
    for fag in FAG:
        if fag in t:
            return fag
    return None

def hent_ukeplan():
    response = requests.get(URL)
    soup = BeautifulSoup(response.content, "html.parser")

    lekser = []
    for link in soup.find_all("a", href=True):
        href = link['href']
        if KLASSE.lower() in link.text.lower() and f"uke {UKE}" in link.text.lower():
            # Vi har funnet riktig ukeplan
            # Henter PDF/HTML-innhold
            pdf_url = href
            # Her kan du velge å laste ned PDF og parse med pdfplumber,
            # eller hente HTML-tabell hvis tilgjengelig
            lekser.append({"tekst": f"Ukeplan link: {pdf_url}", "ukedag": None, "fag": None})
    return lekser

def parse_lekser(fil_tekster):
    result = []
    for tekst in fil_tekster:
        if er_planleggingsdag(tekst):
            continue
        if not gyldig_lekse(tekst):
            continue
        fag = finn_fag(tekst)
        if not fag:
            fag = None
        # Prøv å hente ukedag hvis den står i teksten
        ukedag = None
        for dag in UKEDAGER:
            if dag.lower() in tekst.lower():
                ukedag = dag
                break
        result.append({
            "tekst": tekst.strip(),
            "ukedag": ukedag,
            "fag": fag
        })
    return result

def main():
    fil_tekster = [
        # Her legger du inn teksten hentet fra PDF eller nettside
        "Les i leseboken din i 15 minutter. Oppdater leseloggen i Classroom etter at du har lest. Tirsdag",
        "Planleggingsdag Fredag",
        "Journeys Be able to talk about travel destination. Mandag. Engelsk"
    ]

    data = {
        "klasse": KLASSE,
        "lekser": parse_lekser(fil_tekster),
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(f"ukeplan-{KLASSE}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
