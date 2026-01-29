import requests
import re
import json
import io
from bs4 import BeautifulSoup
from datetime import datetime
from PyPDF2 import PdfReader
from docx import Document

BASE_URL = "https://www.bergen.kommune.no"
INDEX_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"

KLASSE_MØNSTER = [
    r"\b8\s*e\b",
    r"\b8\.?\s*klasse\s*e\b"
]

STIKKORD = [
    "lekse",
    "prøve",
    "innlevering",
    "presentasjon",
    "framføring",
    "øving",
    "øvelse"
]

def hent_index():
    r = requests.get(INDEX_URL, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def finn_nyeste_uke_lenke(soup):
    uke_lenker = []

    for a in soup.find_all("a", href=True):
        tekst = a.get_text(" ", strip=True).lower()
        href = a["href"]

        if "uke" not in tekst:
            continue

        if not any(re.search(k, tekst) for k in KLASSE_MØNSTER):
            continue

        tall = re.findall(r"\b\d{1,2}\b", tekst)
        if not tall:
            continue

        uke = int(tall[0])
        uke_lenker.append((uke, href))

    if not uke_lenker:
        raise RuntimeError("Ingen ukeplan funnet")

    uke_lenker.sort(key=lambda x: x[0], reverse=True)
    url = uke_lenker[0][1]

    if url.startswith("/"):
        url = BASE_URL + url

    return url

def last_ned_fil(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.headers.get("Content-Type", ""), r.content

def tekst_fra_pdf(data):
    reader = PdfReader(io.BytesIO(data))
    tekst = []
    for side in reader.pages:
        t = side.extract_text()
        if t:
            tekst.extend(t.splitlines())
    return tekst

def tekst_fra_docx(data):
    doc = Document(io.BytesIO(data))
    return [p.text for p in doc.paragraphs if p.text.strip()]

def filtrer_lister(linjer):
    funn = []
    for linje in linjer:
        lav = linje.lower()
        if not any(s in lav for s in STIKKORD):
            continue

        dato = None
        m = re.search(r"\b\d{1,2}[./-]\d{1,2}([./-]\d{2,4})?\b", linje)
        if m:
            dato = m.group(0)

        funn.append({
            "tekst": linje.strip(),
            "dato": dato
        })
    return funn

def main():
    soup = hent_index()
    fil_url = finn_nyeste_uke_lenke(soup)

    ctype, data = last_ned_fil(fil_url)

    if "pdf" in ctype:
        linjer = tekst_fra_pdf(data)
    elif "word" in ctype or "officedocument" in ctype:
        linjer = tekst_fra_docx(data)
    else:
        raise RuntimeError("Ukjent filtype")

    resultat = filtrer_lister(linjer)

    with open("ukeplan-8E.json", "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)

    print("OK", len(resultat), "oppføringer")

if __name__ == "__main__":
    main()
