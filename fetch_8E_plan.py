import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO

from PyPDF2 import PdfReader
from docx import Document


BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"

KLASSE = "8E"
UTDATA_FIL = "ukeplan-8E.json"

KLASSE_MØNSTER = [
    r"\b8e\b",
    r"8\.?\s*e",
    r"klasse\s*8e"
]


def hent_html(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def hent_fil(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.content


def finn_nyeste_uke_url(soup):
    uker = []

    for a in soup.find_all("a", href=True):
        tekst = a.get_text(" ").lower()
        m = re.search(r"uke\s*(\d{1,2})", tekst)
        if not m:
            continue

        uke = int(m.group(1))
        href = a["href"]

        if href.startswith("/"):
            href = BASE_URL + href

        uker.append((uke, href))

    if not uker:
        raise RuntimeError("Fant ingen uker")

    uker.sort(key=lambda x: x[0], reverse=True)
    return uker[0][0], uker[0][1]


def finn_alle_filer(soup):
    filer = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        lav = href.lower()
        if not any(ext in lav for ext in [".pdf", ".doc", ".docx"]):
            continue

        if href.startswith("/"):
            href = BASE_URL + href

        filer.append(href)

    if not filer:
        raise RuntimeError("Fant ingen filer på uke-siden")

    return filer


def les_pdf(data):
    reader = PdfReader(BytesIO(data))
    linjer = []

    for side in reader.pages:
        t = side.extract_text()
        if t:
            linjer.extend(t.splitlines())

    return linjer


def les_docx(data):
    doc = Document(BytesIO(data))
    linjer = []

    for p in doc.paragraphs:
        if p.text.strip():
            linjer.append(p.text.strip())

    return linjer


def finn_8e_fil(fil_urler):
    for url in fil_urler:
        lav = url.lower()
        if "8e" in lav:
            return url

    for url in fil_urler:
        data = hent_fil(url)

        if url.lower().endswith(".pdf"):
            tekst = les_pdf(data)
        else:
            tekst = les_docx(data)

        samlet = " ".join(tekst).lower()
        if any(re.search(m, samlet) for m in KLASSE_MØNSTER):
            return url

    raise RuntimeError("Fant ingen ukeplan for 8E")


def filtrer_innhold(linjer):
    lekser = []
    prover = []

    for linje in linjer:
        lav = linje.lower()

        if "lekse" in lav:
            lekser.append(linje)

        if "prøve" in lav or "test" in lav:
            prover.append(linje)

    return lekser, prover


def main():
    start_html = hent_html(START_URL)
    start_soup = BeautifulSoup(start_html, "html.parser")

    uke_nummer, uke_url = finn_nyeste_uke_url(start_soup)

    uke_html = hent_html(uke_url)
    uke_soup = BeautifulSoup(uke_html, "html.parser")

    fil_urler = finn_alle_filer(uke_soup)
    fil_url = finn_8e_fil(fil_urler)

    fil_data = hent_fil(fil_url)

    if fil_url.lower().endswith(".pdf"):
        linjer = les_pdf(fil_data)
    else:
        linjer = les_docx(fil_data)

    lekser, prover = filtrer_innhold(linjer)

    resultat = {
        "uke": uke_nummer,
        "klasse": KLASSE,
        "kilde": fil_url,
        "lekser": lekser,
        "prover": prover
    }

    with open(UTDATA_FIL, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
