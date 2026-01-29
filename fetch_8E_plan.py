#!/usr/bin/env python3
import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import date, datetime
from PyPDF2 import PdfReader
from docx import Document

BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUT_FILE = "ukeplan-8E.json"
KLASSE = "8E"
REQ_TIMEOUT = 25

# Fagkart med språkfag separat
SUBJECT_MAP = {
    "norsk": ["norsk"], 
    "matematikk": ["matematikk", "matte", "math"], 
    "engelsk": ["engelsk"],  
    "engelsk_fordypning": ["engelsk fordypning"],  
    "spansk": ["spansk", "spanish"], 
    "fransk": ["fransk", "french"], 
    "tysk": ["tysk", "german"], 
    "alf": ["alf", "arbeidslivsfag"], 
    "naturfag": ["naturfag", "science"], 
    "krle": ["krle", "religion"], 
    "samfunnsfag": ["samfunnsfag", "social"], 
    "kroppsøving": ["kroppsøving", "gym", "pe"], 
    "kunst": ["kunst", "art", "k&h", "kunst & håndverk", "k / h"], 
    "valgfag": ["valgfag"]
}

UKEDAGER = {
    "mandag": 1, "tirsdag": 2, "onsdag": 3, "torsdag": 4, "fredag": 5, 
    "lørdag": 6, "lordag": 6, "søndag": 7, "sondag": 7
}

PAGE_REF_RE = re.compile(r"(?:side|s\.?)\s*[:]?\s*(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?", re.IGNORECASE)

LEKSE_KEYWORDS = ["lekse","les","innlever","assignment","practice","presentasjon","presentere","video","øve","øving"]
PROVE_KEYWORDS = ["prøve","test"]

def hent_html(url):
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.text

def hent_fil_data(url):
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.headers.get("content-type", ""), r.content

def les_pdf(data):
    reader = PdfReader(BytesIO(data))
    lines = []
    for p in reader.pages:
        t = p.extract_text()
        if t:
            lines.extend([l.strip() for l in t.splitlines() if l.strip()])
    return lines

def les_docx(data):
    doc = Document(BytesIO(data))
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

def date_from_week_and_weekday(year_guess, uke_nummer, weekday_index):
    for y in (year_guess, year_guess-1, year_guess+1):
        try:
            return date.fromisocalendar(y, uke_nummer, weekday_index)
        except: pass
    return None

def join_lines(lines):
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        while i+1 < len(lines) and not re.search(r"[.:?!]$", ln) and lines[i+1][0].islower():
            ln += " " + lines[i+1]
            i += 1
        out.append(ln)
        i += 1
    return out

def find_subject(text):
    low = text.lower()
    for key, variants in SUBJECT_MAP.items():
        for v in variants:
            if re.search(r"\b"+re.escape(v)+r"\b", low):
                return key
    return None

def extract_page(text):
    m = PAGE_REF_RE.search(text)
    if m:
        if m.group(2):
            return f"side {m.group(1)}-{m.group(2)}"
        return f"side {m.group(1)}"
    return None

def split_into_day_fag_blocks(lines):
    blocks = []
    current_day = None
    buf = []

    for ln in lines:
        low = ln.lower()
        # start parsing etter overskrift
        if "dag fag lekser" in low:
            continue

        # finn dag
        found_day = None
        for dag in UKEDAGER.keys():
            if dag in low:
                found_day = dag.capitalize()
                break
        if found_day:
            if buf and current_day:
                blocks.extend(split_fag_blocks(buf, current_day))
            current_day = found_day
            buf = []
            continue
        buf.append(ln)

    if buf and current_day:
        blocks.extend(split_fag_blocks(buf, current_day))
    return blocks

def split_fag_blocks(lines, day):
    """Splitter linjer per fag ved å bruke SUBJECT_MAP AI-lignende."""
    blocks = []
    current_fag = None
    buf = []

    for ln in lines:
        found_fag = find_subject(ln)
        if found_fag:
            if buf and current_fag:
                blocks.append((day, current_fag, " ".join(buf).strip()))
                buf = []
            current_fag = found_fag
            # Hvis flere fag på samme linje, splitter vi etter ord
            remainder = ln
            while True:
                for key, variants in SUBJECT_MAP.items():
                    for v in variants:
                        match = re.search(r"\b"+re.escape(v)+r"\b", remainder.lower())
                        if match:
                            if current_fag != key:
                                if buf:
                                    blocks.append((day, current_fag, " ".join(buf).strip()))
                                    buf = []
                                current_fag = key
                            remainder = remainder[match.end():].strip()
                            break
                    else:
                        continue
                    break
                else:
                    break
            buf.append(ln)
        else:
            buf.append(ln)

    if buf and current_fag:
        blocks.append((day, current_fag, " ".join(buf).strip()))
    return blocks

def process_block(day, text, uke_nummer, fag):
    year = date.today().year
    idx = UKEDAGER.get(day.lower(), None)
    dt = None
    if idx:
        dt = date_from_week_and_weekday(year, uke_nummer, idx)
    return [{
        "tekst": text.strip(),
        "dato": dt.isoformat() if dt else None,
        "ukedag": day,
        "side_eller_oppgave": extract_page(text),
        "fag": fag
    }]

def finn_best_match(filer):
    for url in filer:
        try:
            ctype, data = hent_fil_data(url)
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                lines = les_pdf(data)
            elif url.lower().endswith((".doc",".docx")):
                lines = les_docx(data)
            else:
                continue
            combined_text = " ".join(lines).lower()
            if re.search(r"\b8\.?\s*e\b", combined_text):
                return url, lines
        except:
            continue
    return None, None

def main():
    index_html = hent_html(START_URL)
    index_soup = BeautifulSoup(index_html, "html.parser")

    uke_lenker = []
    for a in index_soup.find_all("a", href=True):
        tekst = a.get_text(" ", strip=True).lower()
        href = a["href"]
        m = re.search(r"uke\s*(\d{1,2})", tekst)
        if m:
            uke = int(m.group(1))
            url = href if href.startswith("http") else BASE_URL + href
            uke_lenker.append((uke, url))
    if not uke_lenker:
        raise RuntimeError("Ingen uke-lenker funnet")

    cur_uke = date.today().isocalendar()[1]
    uke_nummer, uke_url = min(uke_lenker, key=lambda x: abs(x[0]-cur_uke))

    uke_html = hent_html(uke_url)
    uke_soup = BeautifulSoup(uke_html, "html.parser")

    filer = []
    for a in uke_soup.find_all("a", href=True):
        href = a["href"]
        if "/api/rest/filer/" in href.lower() or href.lower().endswith((".pdf",".doc",".docx")):
            filer.append(href if href.startswith("http") else BASE_URL + href)
    if not filer:
        raise RuntimeError("Fant ingen filer")

    fil_url, raw_lines = finn_best_match(filer)
    if not fil_url:
        raise RuntimeError("Fant ingen fil for klasse " + KLASSE)

    lines = join_lines(raw_lines)
    day_fag_blocks = split_into_day_fag_blocks(lines)

    all_tasks = []
    for day, fag, txt in day_fag_blocks:
        all_tasks.extend(process_block(day, txt, uke_nummer, fag))

    lekser = [t for t in all_tasks if any(k in t["tekst"].lower() for k in LEKSE_KEYWORDS)]
    prover = [t for t in all_tasks if any(k in t["tekst"].lower() for k in PROVE_KEYWORDS)]

    output = {
        "uke": uke_nummer,
        "klasse": KLASSE,
        "kilde": fil_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Ferdig, lagret i", OUT_FILE)
    print("Lekser:", len(lekser), "Prøver:", len(prover))

if __name__ == "__main__":
    main()
