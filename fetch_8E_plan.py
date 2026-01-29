#!/usr/bin/env python3
import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import date, datetime
from PyPDF2 import PdfReader
from docx import Document

# -------------- CONFIG ----------------
BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUT_FILE = "ukeplan-8E.json"
KLASSE = "8E"
REQ_TIMEOUT = 25

SUBJECT_MAP = {
    "norsk": ["norsk"], "matematikk": ["matematikk", "matte", "math"], "engelsk": ["engelsk", "english"],
    "spansk": ["spansk", "spanish"], "fransk": ["fransk", "french"], "tysk": ["tysk", "german"],
    "naturfag": ["naturfag", "science"], "krle": ["krle", "religion"], "samfunnsfag": ["samfunnsfag", "social"],
    "kroppsøving": ["kroppsøving", "gym", "pe"], "kunst": ["kunst", "art"], "valgfag": ["valgfag"], "språk": ["språk"]
}

UKEDAGER = {
    "mandag": 1, "tirsdag": 2, "onsdag": 3, "torsdag": 4, "fredag": 5, "lørdag": 6, "lordag": 6, "søndag": 7, "sondag": 7
}

KLASSE_MØNSTER_URL = [r"\b8e\b", r"\b8\.?e\b", r"\b8\s*e\b", r"pdf8e"]

PAGE_REF_RE = re.compile(r"(?:side|s\.?)\s*[:]?\s*(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)")

# -------------- HENT FILER ----------------
def hent_html(url):
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.text

def hent_fil_data(url):
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.headers.get("content-type", ""), r.content

def les_pdf(data):
    try:
        reader = PdfReader(BytesIO(data))
    except:
        return []
    lines = []
    for p in reader.pages:
        t = p.extract_text()
        if t:
            lines.extend([l.strip() for l in t.splitlines() if l.strip()])
    return lines

def les_docx(data):
    try:
        doc = Document(BytesIO(data))
    except:
        return []
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

# -------------- UKEDAG / DATO ----------------
def date_from_week_and_weekday(year_guess, uke_nummer, weekday_index):
    for y in (year_guess, year_guess-1, year_guess+1):
        try:
            return date.fromisocalendar(y, uke_nummer, weekday_index)
        except: pass
    return None

def try_parse_date_str(s):
    s = s.strip()
    m = re.match(r"^(\d{1,2})[./](\d{1,2})$", s)
    if m:
        d, mo = int(m[1]), int(m[2])
        y = date.today().year
        try: return date(y, mo, d)
        except: return None
    return None

# -------------- PARSING ----------------
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

def split_into_day_blocks(lines):
    blocks = []
    current_day = None
    buf = []
    started = False
    for ln in lines:
        low = ln.lower()
        if not started:
            if "dag fag lekser" in low:
                started = True
            continue
        found_day = None
        for dag in UKEDAGER.keys():
            if dag in low:
                found_day = dag
                break
        if found_day:
            if buf:
                blocks.append((current_day, " ".join(buf).strip()))
                buf = []
            current_day = found_day.capitalize()
            continue
        buf.append(ln)
    if buf:
        blocks.append((current_day, " ".join(buf).strip()))
    return blocks

def extract_page(text):
    m = PAGE_REF_RE.search(text)
    if m:
        if m.group(2):
            return f"side {m.group(1)}-{m.group(2)}"
        return f"side {m.group(1)}"
    return None

def find_subject(text):
    low = text.lower()
    for key, variants in SUBJECT_MAP.items():
        for v in variants:
            if v in low:
                return key
    return None

def process_block(day, text, uke_nummer):
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
        "fag": find_subject(text)
    }]

# -------------- FINN FIL ----------------
def finn_best_match(filer):
    for url in filer:
        for pat in KLASSE_MØNSTER_URL:
            if re.search(pat, url.lower()):
                ctype, data = hent_fil_data(url)
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    lines = les_pdf(data)
                else:
                    lines = les_docx(data)
                return url, lines
    return None, None

def main():
    index_html = hent_html(START_URL)
    index_soup = BeautifulSoup(index_html, "html.parser")

    # finn uke-lenker
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
    blocks = split_into_day_blocks(lines)

    all_tasks = []
    for day, txt in blocks:
        all_tasks.extend(process_block(day, txt, uke_nummer))

    lekser = [t for t in all_tasks if any(k in t["tekst"].lower() for k in ["lekse","les","innlever","assignment","practice","presentasjon","presentere","video","øve","øving"])]
    prover = [t for t in all_tasks if any(k in t["tekst"].lower() for k in ["prøve","test"])]

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
