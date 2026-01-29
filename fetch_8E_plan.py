import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO

from PyPDF2 import PdfReader
from docx import Document


BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"

KLASSE_MØNSTER = [
    r"\b8e\b",
    r"8\s*e",
    r"klasse\s*8e"
]

UTDATA_FIL = "ukeplan-8E.json"


def hent_html(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def finn_nyeste_uke_url(soup):
    uker = []

    for a in soup.find_all("a", href=True):
        tekst = a.get_text(" ").lower()
        match = re.search(r"uke\s*(\d{1,2})", tekst)
        if not match:
            continue

        uke = int(match.group(1))
        href = a["href"]

        if href.startswith("/"):
            href = BASE_URL + href

        uker.append((uke, href))

    if not uker:
        raise RuntimeError("Fant ingen uker")

    uker.sort(key=lambda x: x[0], reverse=True)
    return uker[0][1], uker[0][0]


def finn_klasse_fil_url(soup):
    for a in soup.find_all("a", href=True):
        tekst = a.get_text(" ").lower()
        href = a["href"].lower()

        if not any(re.search(m, tekst) for m in KLASSE_MØNSTER):
            continue

        if not any(ext in href for ext in [".pdf", ".doc", ".docx"]):
            continue

        if href.startswith("/"):
            href = BASE_URL + href

        return href

    raise RuntimeError("Fant ikke klasse 8E")


def hent_fil(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.content


def les_pdf(data):
    reader = PdfReader(BytesIO(data))
    tekst = []

    for side in reader.pages:
        t = side.extract_text()
        if t:
            tekst.extend(t.splitlines())

    return tekst


def les_docx(data):
    doc = Document(BytesIO(data))
    tekst = []

    for p in doc.paragraphs:
        if p.text.strip():
            tekst.append(p.text.strip())

    return tekst


def filtrer_lekser_og_prover(linjer):
    lekser = []
    prover = []

    for linje in linjer:
        l = linje.lower()

        if "lekse" in l:
            lekser.append(linje)

        if "prøve" in l or "test" in l:
            prover.append(linje)

    return {
        "lekser": lekser,
        "prover": prover
    }


def main():
    start_html = hent_html(START_URL)
    start_soup = BeautifulSoup(start_html, "html.parser")

    uke_url, uke_nummer = finn_nyeste_uke_url(start_soup)

    uke_html = hent_html(uke_url)
    uke_soup = BeautifulSoup(uke_html, "html.parser")

    fil_url = finn_klasse_fil_url(uke_soup)

    fil_data = hent_fil(fil_url)

    if fil_url.endswith(".pdf"):
        linjer = les_pdf(fil_data)
    else:
        linjer = les_docx(fil_data)

    samlet = " ".join(linjer).lower()
    if not any(re.search(m, samlet) for m in KLASSE_MØNSTER):
        raise RuntimeError("Dokument matcher ikke 8E")

    innhold = filtrer_lekser_og_prover(linjer)

    resultat = {
        "uke": uke_nummer,
        "klasse": "8E",
        "kilde": fil_url,
        "lekser": innhold["lekser"],
        "prover": innhold["prover"]
    }

    with open(UTDATA_FIL, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
