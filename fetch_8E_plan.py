#!/usr/bin/env python3
"""
fetch_8E_plan.py

Robust scraper for Mjølkeråen skole ukeplan.
Produces ukeplan-8E.json with tasks split by day and subject.
"""

import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import date, datetime

# PDF / DOCX
from PyPDF2 import PdfReader
from docx import Document

# Optional OCR fallback, only used if imports succeed and tesseract is installed.
try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUT_FILE = "ukeplan-8E.json"
CLASS_KEY = "8E"
TIMEOUT = 25

# subject map. special case: english and english_fordypning separate
SUBJECT_MAP = {
    "norsk": ["norsk"],
    "matematikk": ["matematikk", "matte", "math"],
    "engelsk_fordypning": ["engelsk fordypning"],
    "engelsk": ["engelsk", "english"],
    "spansk": ["spansk", "spanish"],
    "fransk": ["fransk", "french"],
    "tysk": ["tysk", "german"],
    "alf": ["alf", "arbeidslivsfag"],
    "naturfag": ["naturfag", "science"],
    "krle": ["krle"],
    "samfunnsfag": ["samfunnsfag", "social"],
    "kroppsøving": ["kroppsøving", "gym", "pe"],
    "kunst": ["kunst", "art", "k&h", "k & h", "kunst & håndverk", "kunst/håndverk", "kunst / håndverk"],
    "valgfag": ["valgfag"]
}

# keyword lists
HOMEWORK_KEYWORDS = [
    "lekse", "les", "innlever", "assignment", "practice", "presentasjon", "presentere",
    "video", "øve", "øving", "framføring", "fremføring", "fremføring"
]
TEST_KEYWORDS = ["prøve", "test"]

# weekdays mapping norwegian lower -> ISO weekday
WEEKDAY_MAP = {
    "mandag": 1, "tirsdag": 2, "onsdag": 3, "torsdag": 4, "fredag": 5,
    "lørdag": 6, "lordag": 6, "søndag": 7, "sondag": 7
}

# regexes
PAGE_RE = re.compile(r"(?:side|s\.?)\s*[:]? *(\d{1,3})(?:\s*[–—-]\s*(\d{1,3}))?", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)")
CLASS_RE = re.compile(r"\b8\.?\s*e\b", re.IGNORECASE)

# build subject regex with longer variants first
_subject_variants = []
for key, variants in SUBJECT_MAP.items():
    for v in variants:
        _subject_variants.append(re.escape(v))
_subject_variants.sort(key=len, reverse=True)
SUBJECT_RE = re.compile(r"\b(" + r"|".join(_subject_variants) + r")\b", re.IGNORECASE)

# helper http
def get_text(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def download_file(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    return ctype, r.content

# extract text from pdf using PyPDF2
def extract_text_from_pdf_bytes(data):
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return []
    lines = []
    for p in reader.pages:
        try:
            txt = p.extract_text()
        except Exception:
            txt = None
        if txt:
            for ln in txt.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)
    return lines

# docx
def extract_text_from_docx_bytes(data):
    try:
        doc = Document(BytesIO(data))
    except Exception:
        return []
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

# OCR fallback for scanned PDFs
def ocr_pdf_bytes(data):
    if not OCR_AVAILABLE:
        return []
    try:
        images = convert_from_bytes(data)
    except Exception:
        return []
    lines = []
    for img in images:
        txt = pytesseract.image_to_string(img, lang="nor+eng")
        for ln in txt.splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)
    return lines

# find week links on index page
def find_week_links(index_html):
    soup = BeautifulSoup(index_html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"]
        # match "uke X" in text
        m = re.search(r"uke\s*(\d{1,2})", text)
        if not m:
            m = re.search(r"uke[-_/ ]?(\d{1,2})", href.lower())
        if m:
            uke = int(m.group(1))
            url = href if href.startswith("http") else BASE_URL + href
            links.append((uke, url))
    # unique per uke keep first
    unique = {}
    for u, url in links:
        if u not in unique:
            unique[u] = url
    return [(u, unique[u]) for u in unique]

# choose current week or nearest
def choose_week(week_links):
    if not week_links:
        raise RuntimeError("Ingen uke-lenker funnet")
    now_week = date.today().isocalendar()[1]
    for u, url in week_links:
        if u == now_week:
            return u, url
    # nearest by week number difference
    return min(week_links, key=lambda x: abs(x[0] - now_week))

# collect file links on week page
def find_file_links(week_html):
    soup = BeautifulSoup(week_html, "html.parser")
    files = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        l = href.lower()
        if "/api/rest/filer/" in l or l.endswith(".pdf") or l.endswith(".docx") or l.endswith(".doc"):
            url = href if href.startswith("http") else BASE_URL + href
            if url not in files:
                files.append(url)
    return files

# detect correct file by reading content for class marker
def find_class_file(file_urls):
    for url in file_urls:
        try:
            ctype, data = download_file(url)
        except Exception:
            continue
        lines = []
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            lines = extract_text_from_pdf_bytes(data)
            if not lines and OCR_AVAILABLE:
                lines = ocr_pdf_bytes(data)
        elif url.lower().endswith((".doc", ".docx")):
            lines = extract_text_from_docx_bytes(data)
        combined = " ".join(lines).lower()
        if CLASS_RE.search(combined) or re.search(r"\b8e\b", url.lower()):
            return url, lines
    return None, None

# join broken lines: hyphenated and continued lines
def normalize_and_join_lines(lines):
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        # remove leading page numbers or header timestamps
        ln = re.sub(r"^\s*\d{1,2}:\d{2}\s*", "", ln)
        # remove lines that are pure times or headers like "Time Tid Mandag Tirsdag"
        if re.match(r"^(time\b|tid\b)", ln.strip().lower()):
            i += 1
            continue
        # merge hyphenated words
        while ln.endswith("-") and i + 1 < len(lines):
            i += 1
            ln = ln[:-1] + lines[i].strip()
        # merge continuation lines heuristics
        while i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if not nxt:
                break
            # if next starts with lowercase, or current does not end with punctuation, join
            if nxt[0].islower() or not re.search(r"[.?!:]$", ln):
                ln = ln + " " + nxt
                i += 1
                continue
            break
        ln = ln.strip()
        if ln:
            out.append(ln)
        i += 1
    return out

# remove header and footer noise
def filter_noise(lines):
    out = []
    for ln in lines:
        low = ln.lower()
        if "arbeidsplan" in low and re.search(r"\b8\b|\b8e\b", low):
            continue
        if "mjølkeråen skole" in low or "mjølkeråen" in low:
            continue
        if re.match(r"^side\s*\d+$", low):
            continue
        out.append(ln)
    return out

# split into day blocks. start after "dag fag lekser"
def split_to_day_blocks(lines):
    joined = []
    started = False
    for ln in lines:
        low = ln.lower()
        if not started:
            if "dag fag lekser" in low or "dag fag leks er" in low or re.search(r"\bdag\b.*\bfag\b.*\blekse", low):
                started = True
                continue
            # also if we find a line that is exactly "dag fag lekser" with case variants
            continue
        joined.append(ln)
    # if not started, treat whole text as one block
    if not started:
        joined = lines[:]
    # now split by explicit weekday names
    blocks = []
    cur_day = None
    cur_buf = []
    for ln in joined:
        low = ln.lower()
        day_found = None
        for d in WEEKDAY_MAP.keys():
            if re.search(r"\b" + re.escape(d) + r"\b", low):
                day_found = d
                break
        if day_found:
            # flush previous
            if cur_buf and cur_day:
                blocks.append((cur_day, " ".join(cur_buf).strip()))
            cur_day = day_found.capitalize()
            cur_buf = []
            # if the rest of the line after day contains text, keep it
            remainder = re.sub(r".*\b" + re.escape(day_found) + r"\b", "", low, count=1).strip()
            if remainder:
                cur_buf.append(remainder)
            continue
        cur_buf.append(ln)
    if cur_buf and cur_day:
        blocks.append((cur_day, " ".join(cur_buf).strip()))
    return blocks

# split a day block into per-subject segments
def split_day_block_into_subjects(day_block_text):
    text = day_block_text.strip()
    # find all subject matches with positions
    matches = list(SUBJECT_RE.finditer(text))
    if not matches:
        # try fallback split by double spaces or punctuation that likely separates items
        parts = [p.strip() for p in re.split(r"\s{2,}|\s*;\s*|\s*\/\s*", text) if p.strip()]
        return [(None, p) for p in parts]
    segments = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        subj_text = m.group(0)
        seg_text = text[start:end].strip()
        # normalize subject key
        subj_key = subject_key_from_text(subj_text)
        if not subj_key:
            # try inspect seg_text for first subject occurrence mapping
            subj_key = subject_key_from_text(seg_text)
        segments.append((subj_key, seg_text))
    return segments

def subject_key_from_text(txt):
    low = txt.lower()
    for key, variants in SUBJECT_MAP.items():
        for v in variants:
            if re.search(r"\b" + re.escape(v) + r"\b", low):
                return key
    return None

def extract_page_ref(text):
    m = PAGE_RE.search(text)
    if not m:
        return None
    if m.group(2):
        return f"side {m.group(1)}-{m.group(2)}"
    return f"side {m.group(1)}"

def parse_date_from_block_or_weekday(block_text, day_name, week_number):
    # try explicit date token
    for tok in DATE_TOKEN_RE.findall(block_text):
        dt = try_parse_date(tok)
        if dt:
            return dt
    # fallback to compute from week + weekday
    if day_name:
        idx = WEEKDAY_MAP.get(day_name.lower())
        if idx:
            try_years = [date.today().year, date.today().year - 1, date.today().year + 1]
            for y in try_years:
                try:
                    return date.fromisocalendar(y, week_number, idx)
                except Exception:
                    continue
    return None

def try_parse_date(s):
    s = s.strip()
    # yyyy-mm-dd
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except Exception:
            return None
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", s)
    if m:
        d, mo, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yy < 100:
            yy += 2000
        try:
            return date(yy, mo, d)
        except Exception:
            return None
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})$", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = date.today().year
        try:
            return date(y, mo, d)
        except Exception:
            return None
    return None

# decide if a segment is homework or test using keyword heuristics and simple rules
def classify_segment(text):
    low = text.lower()
    is_homework = any(k in low for k in HOMEWORK_KEYWORDS)
    is_test = any(k in low for k in TEST_KEYWORDS)
    return is_homework, is_test

# core processing
def process_lines_into_tasks(raw_lines, week_number):
    # normalize and filter
    norm = normalize_and_join_lines(raw_lines)
    norm = filter_noise(norm)
    blocks = split_to_day_blocks(norm)
    tasks = []

    for day_name, block_text in blocks:
        # split by subjects inside the day block
        subj_segs = split_day_block_into_subjects(block_text)
        for subj_key, seg_text in subj_segs:
            seg_text_clean = seg_text.strip()
            if not seg_text_clean:
                continue
            # remove leading subject word if present
            if subj_key:
                # remove the first occurrence of any variant to avoid repetition
                for v in SUBJECT_MAP.get(subj_key, []):
                    seg_text_clean = re.sub(r"\b" + re.escape(v) + r"\b", "", seg_text_clean, count=1, flags=re.IGNORECASE).strip()
            # parse date for this block
            dt = parse_date_from_block_or_weekday(seg_text_clean, day_name, week_number)
            page_ref = extract_page_ref(seg_text_clean)
            is_homework, is_test = classify_segment(seg_text_clean)
            # keep only if it looks like a task (homework or test or has page ref)
            if not (is_homework or is_test or page_ref):
                # skip pure schedule lines or leftover headings
                continue
            task = {
                "tekst": seg_text_clean,
                "dato": dt.isoformat() if isinstance(dt, date) else None,
                "ukedag": day_name,
                "side_eller_oppgave": page_ref,
                "fag": subj_key
            }
            tasks.append(task)
    return tasks

def main():
    index_html = get_text(START_URL)
    week_links = find_week_links(index_html)
    week_num, week_url = choose_week(week_links)

    week_html = get_text(week_url)
    file_urls = find_file_links(week_html)
    if not file_urls:
        raise RuntimeError("Fant ingen filer på uke-siden")

    file_url, raw_lines = find_class_file(file_urls)
    if not file_url:
        raise RuntimeError("Fant ingen fil for klasse " + CLASS_KEY)

    # process
    tasks = process_lines_into_tasks(raw_lines, week_num)

    # split to lekser and prover lists
    lekser = [t for t in tasks if any(k in t["tekst"].lower() for k in HOMEWORK_KEYWORDS)]
    prover = [t for t in tasks if any(k in t["tekst"].lower() for k in TEST_KEYWORDS)]

    out = {
        "uke": week_num,
        "klasse": CLASS_KEY,
        "kilde": file_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Ferdig. Lagret:", OUT_FILE)
    print("Lekser:", len(lekser), "Prøver:", len(prover))

if __name__ == "__main__":
    main()
