import requests
import pdfplumber
import datetime
import json
import re
from io import BytesIO

KLASSE = "8E"
BASE = "https://www.bergen.kommune.no"

UKEPLAN_OVERSIKT = (
    "https://www.bergen.kommune.no/omkommunen/"
    "avdelinger/mjolkeraen-skole/arbeidsplaner"
)

UKEDAGER = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag"]

PRØVE_ORD = [
    "prøve",
    "test",
    "fremføring",
    "presentasjon",
    "presentation"
]

FAG_MAP = {
    "norsk": "norsk",
    "matematikk": "matematikk",
    "samfunnsfag": "samfunnsfag",
    "naturfag": "naturfag",
    "krle": "krle",
    "kroppsøving": "kroppsøving",
    "kunst": "kunst og håndverk",
    "k&h": "kunst og håndverk",
    "engelsk": "engelsk",
    "engelsk fordypning": "engelsk fordypning",
    "spansk": "spansk",
    "fransk": "fransk",
    "tysk": "tysk",
    "alf": "alf",
    "arbeidslivsfag": "alf"
}

SIDE_RE = re.compile(r"s\.?\s*\d+(\s*[–-]\s*\d+)?", re.I)

def dagens_uke():
    return datetime.date.today().isocalendar().week

def uke_til_dato(uke, ukedag):
    year = datetime.date.today().year
    mandag = datetime.date.fromisocalendar(year, uke, 1)
    return mandag + datetime.timedelta(days=UKEDAGER.index(ukedag))

def hent_html(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def finn_uke_side():
    html = hent_html(UKEPLAN_OVERSIKT)
    uke = dagens_uke()

    m = re.search(
        rf'href="([^"]*uke-{uke}[^"]*)"',
        html,
        re.I
    )

    if not m:
        raise RuntimeError("Fant ikke uke-side")

    return BASE + m.group(1)

def finn_pdf_for_klasse(uke_url):
    html = hent_html(uke_url)

    pdfs = re.findall(
        r'href="(/api/rest/filer/[^"]+)"',
        html,
        re.I
    )

    if not pdfs:
        raise RuntimeError("Fant ingen PDF-er på uke-siden")

    for rel in pdfs:
        url = BASE + rel
        try:
            r = requests.get(url, timeout=20)
            with pdfplumber.open(BytesIO(r.content)) as pdf:
                first = pdf.pages[0].extract_text().lower()
                if f"arbeidsplan for {KLASSE.lower()}" in first:
                    return url
        except Exception:
            continue

    raise RuntimeError("Fant ingen PDF for klasse " + KLASSE)

def normaliser_fag(linje):
    for k, v in FAG_MAP.items():
        if k in linje:
            return v
    return None

def er_stoy(linje):
    return (
        not linje
        or re.match(r"\d{2}[:.]\d{2}", linje)
        or "arbeidsplan" in linje
        or "mjolkeraen" in linje
        or linje.startswith("tid")
        or linje.startswith("time")
    )

def main():
    uke = dagens_uke()
    uke_side = finn_uke_side()
    pdf_url = finn_pdf_for_klasse(uke_side)

    r = requests.get(pdf_url)
    pdf = pdfplumber.open(BytesIO(r.content))

    lekser = []
    prover = []

    aktiv_dag = None
    aktiv_fag = None
    buffer = ""

    for page in pdf.pages:
        for raw in page.extract_text().splitlines():
            linje = raw.strip()
            low = linje.lower()

            if er_stoy(low):
                continue

            if low in UKEDAGER:
                if buffer and aktiv_fag and aktiv_dag:
                    entry = bygg_entry(buffer, aktiv_dag, aktiv_fag, uke)
                    sorter(entry, lekser, prover)

                aktiv_dag = low
                aktiv_fag = None
                buffer = ""
                continue

            fag = normaliser_fag(low)
            if fag:
                if buffer and aktiv_fag and aktiv_dag:
                    entry = bygg_entry(buffer, aktiv_dag, aktiv_fag, uke)
                    sorter(entry, lekser, prover)

                aktiv_fag = fag
                buffer = linje
                continue

            if aktiv_fag:
                buffer += " " + linje

    if buffer and aktiv_fag and aktiv_dag:
        entry = bygg_entry(buffer, aktiv_dag, aktiv_fag, uke)
        sorter(entry, lekser, prover)

    data = {
        "uke": uke,
        "klasse": KLASSE,
        "kilde": pdf_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.datetime.utcnow().isoformat() + "Z"
    }

    with open("ukeplan-8E.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def bygg_entry(tekst, dag, fag, uke):
    m = SIDE_RE.search(tekst)
    return {
        "tekst": tekst.strip(),
        "ukedag": dag.capitalize(),
        "dato": uke_til_dato(uke, dag).isoformat(),
        "side_eller_oppgave": m.group(0) if m else None,
        "fag": fag
    }

def sorter(entry, lekser, prover):
    if any(w in entry["tekst"].lower() for w in PRØVE_ORD):
        prover.append(entry)
    else:
        lekser.append(entry)

if __name__ == "__main__":
    main()
