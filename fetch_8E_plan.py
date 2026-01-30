import requests
import pdfplumber
import datetime
import json
import re
from io import BytesIO

KLASSE = "8E"

UKEPLAN_URL = "https://www.bergen.kommune.no/skole/mjolkeråen-skole/ukeplaner"

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

SPRÅK = {"spansk", "fransk", "tysk", "engelsk fordypning", "alf"}

UKEDAGER = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag"]

PRØVE_ORD = ["prøve", "test", "fremføring", "presentasjon", "presentation"]

SIDE_RE = re.compile(r"(s\.?\s*\d+(\s*[–-]\s*\d+)?)", re.I)

def dagens_uke():
    return datetime.date.today().isocalendar().week

def finn_pdf_url():
    html = requests.get(UKEPLAN_URL).text
    uke = dagens_uke()

    kandidater = re.findall(r'href="([^"]+)"[^>]*8E', html, re.I)
    if not kandidater:
        raise RuntimeError("Fant ingen PDF for 8E")

    return "https://www.bergen.kommune.no" + kandidater[0]

def uke_til_dato(uke, ukedag):
    year = datetime.date.today().year
    mandag = datetime.date.fromisocalendar(year, uke, 1)
    return mandag + datetime.timedelta(days=UKEDAGER.index(ukedag))

def last_pdf(url):
    r = requests.get(url)
    r.raise_for_status()
    return pdfplumber.open(BytesIO(r.content))

def normaliser_fag(linje):
    for k, v in FAG_MAP.items():
        if k in linje:
            return v
    return None

def er_overskrift(linje):
    return (
        "arbeidsplan" in linje
        or "mjolkeråen" in linje
        or "time" in linje
        or "tid" in linje
        or re.match(r"\d{2}[:.]\d{2}", linje)
    )

def main():
    pdf_url = finn_pdf_url()
    pdf = last_pdf(pdf_url)

    uke = dagens_uke()

    lekser = []
    prover = []

    aktiv_dag = None
    aktiv_fag = None
    buffer = ""

    for page in pdf.pages:
        lines = page.extract_text().splitlines()

        for raw in lines:
            linje = raw.strip()
            low = linje.lower()

            if not linje or er_overskrift(low):
                continue

            if low in UKEDAGER:
                if buffer and aktiv_fag and aktiv_dag:
                    entry = {
                        "tekst": buffer.strip(),
                        "ukedag": aktiv_dag.capitalize(),
                        "dato": uke_til_dato(uke, aktiv_dag).isoformat(),
                        "side_eller_oppgave": None,
                        "fag": aktiv_fag
                    }

                    if any(w in buffer.lower() for w in PRØVE_ORD):
                        prover.append(entry)
                    else:
                        lekser.append(entry)

                aktiv_dag = low
                aktiv_fag = None
                buffer = ""
                continue

            fag = normaliser_fag(low)
            if fag:
                if buffer and aktiv_fag and aktiv_dag:
                    entry = {
                        "tekst": buffer.strip(),
                        "ukedag": aktiv_dag.capitalize(),
                        "dato": uke_til_dato(uke, aktiv_dag).isoformat(),
                        "side_eller_oppgave": None,
                        "fag": aktiv_fag
                    }

                    if any(w in buffer.lower() for w in PRØVE_ORD):
                        prover.append(entry)
                    else:
                        lekser.append(entry)

                aktiv_fag = fag
                buffer = linje
                continue

            if aktiv_fag:
                buffer += " " + linje

    if buffer and aktiv_fag and aktiv_dag:
        entry = {
            "tekst": buffer.strip(),
            "ukedag": aktiv_dag.capitalize(),
            "dato": uke_til_dato(uke, aktiv_dag).isoformat(),
            "side_eller_oppgave": None,
            "fag": aktiv_fag
        }

        if any(w in buffer.lower() for w in PRØVE_ORD):
            prover.append(entry)
        else:
            lekser.append(entry)

    for l in lekser + prover:
        m = SIDE_RE.search(l["tekst"])
        if m:
            l["side_eller_oppgave"] = m.group(1)

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

if __name__ == "__main__":
    main()
