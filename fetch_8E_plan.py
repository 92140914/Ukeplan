import requests
from bs4 import BeautifulSoup
import pdfplumber
import re
import json
from datetime import date, datetime

SKOLE_OVERSIKT = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
KLASSE_STIKKORD = ["8", "e"]  # matcher alt som inneholder både 8 og E
UKE_I_DAG = date.today().isocalendar().week
OUT = f"ukeplan-8E.json"

KEYWORDS = [
    "lekse","oppgave","innlevering","frist","lese","leseboken","leseloggen",
    "øve","presentasjon","fremføring","prøve","test","quiz","eksamen",
    "classroom","video","film"
]

def hent_side(url):
    r = requests.get(url)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def finn_uker(soup):
    result = []
    for a in soup.select("a"):
        txt = a.text.strip().lower()
        m = re.search(r"uke\s*(\d+)", txt)
        if m:
            uke_nr = int(m.group(1))
            href = a.get("href")
            if href:
                result.append((uke_nr, href))
    return result

def velg_nyeste_uke(uker):
    best = None
    diff_min = None
    for uke_nr, href in uker:
        diff = abs(uke_nr - UKE_I_DAG)
        if diff_min is None or diff < diff_min:
            diff_min = diff
            best = href
    return best

def finn_klasse_link(uke_url):
    soup = hent_side(uke_url)
    for a in soup.select("a"):
        txt = a.text.strip().lower()
        if all(k in txt for k in KLASSE_STIKKORD):
            href = a.get("href")
            if href:
                return href
    return None

def hent_pdf_url(klasse_url):
    soup = hent_side(klasse_url)
    for a in soup.select("a"):
        href = a.get("href")
        if href and "/api/rest/filer/" in href:
            return "https://www.bergen.kommune.no" + href
    return None

def parse_pdf(pdf_url):
    lekser = []
    r = requests.get(pdf_url)
    r.raise_for_status()
    with pdfplumber.open(r.content) as pdf:
        tekst = ""
        for p in pdf.pages:
            tekst += (p.extract_text() or "") + "\n"

    lines = [l.strip() for l in tekst.splitlines() if l.strip()]
    current_day = None

    for line in lines:
        low = line.lower()
        for dag in ["mandag","tirsdag","onsdag","torsdag","fredag"]:
            if line.lower().startswith(dag):
                current_day = dag.capitalize()
                break

        if not any(k in low for k in KEYWORDS):
            continue

        if "planleggingsdag" in low:
            lekser.append({
                "tekst": line,
                "ukedag": current_day,
                "dato": datetime.utcnow().strftime("%Y-%m-%d"),
                "type": "planleggingsdag"
            })
            continue

        lekser.append({
            "tekst": line,
            "ukedag": current_day,
            "dato": datetime.utcnow().strftime("%Y-%m-%d")
        })
    return lekser

def main():
    start = hent_side(SKOLE_OVERSIKT)
    uker = finn_uker(start)
    if not uker:
        print("Fant ingen uker")
        return

    uke_link = velg_nyeste_uke(uker)
    uke_url = "https://www.bergen.kommune.no" + uke_link

    klasse_link = finn_klasse_link(uke_url)
    if not klasse_link:
        print("Fant ingen klasse")
        return
    klasse_url = "https://www.bergen.kommune.no" + klasse_link

    pdf_url = hent_pdf_url(klasse_url)
    if not pdf_url:
        print("Fant ingen PDF")
        return

    lekser = parse_pdf(pdf_url)

    data = {
        "uke": UKE_I_DAG,
        "klasse": "8E",
        "kilde": pdf_url,
        "lekser": lekser,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
