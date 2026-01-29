#!/usr/bin/env python3
import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import date, datetime

from PyPDF2 import PdfReader
from docx import Document

# ---------------- CONFIG ----------------
BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUT_FILE = "ukeplan-8E.json"
DEBUG_FILE = "ukeplan-8E-debug.json"
KLASSE = "8E"
REQ_TIMEOUT = 25

# stikkord norsk + engelsk
STIKKORD = [
    "lekse", "innlevering", "prøve", "test",
    "presentasjon", "framføring", "presentere",
    "video", "øvelse", "øving", "øve",
    "assignment", "lesson", "classroom", "les", "practice"
]

# fagnavn og varianter, normalisert til nøkkel
SUBJECT_MAP = {
    "norsk": ["norsk"],
    "matematikk": ["matematikk", "math", "matte"],
    "engelsk": ["engelsk", "english"],
    "spansk": ["spansk", "spanish"],
    "fransk": ["fransk", "french"],
    "tysk": ["tysk", "german"],
    "naturfag": ["naturfag", "science"],
    "krle": ["krle", "religion", "religion and ethics"],
    "samfunnsfag": ["samfunnsfag", "social studies", "social"],
    "kroppsøving": ["kroppsøving", "pe", "gym"],
    "kunst_og_handverk": ["kunst", "kunst/ handverk", "kunst/ håndverk", "kunst og håndverk", "art"],
    "valgfag": ["valgfag"],
    "språk": ["språk", "language"],
    "alf": ["alf", "alf/ språkopplæring"]
}

# mønstre som indikerer klasse i url eller tekst
KLASSE_MØNSTER_URL = [
    r"\b8e\b", r"\b8\.?e\b", r"\b8\s*e\b", r"\bklasse\s*8e\b", r"pdf8e", r".*8e.*"
]

UKEDAGER = {
    "mandag": 1, "tirsdag": 2, "onsdag": 3, "torsdag": 4,
    "fredag": 5, "lørdag": 6, "lordag": 6, "søndag": 7, "sondag": 7
}

# regexer
PAGE_REF_RE = re.compile(r"(?:side|s\.?)\s*[:]?\s*(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?", re.IGNORECASE)
TASK_REF_RE = re.compile(r"(?:oppgave|task)\s*[:]?\s*(\d{1,3})", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(r"(\d{1,4}[./-]\d{1,4}(?:[./-]\d{2,4})?)")
SUBJECT_RE = re.compile("|".join(
    sorted({re.escape(v) for vals in SUBJECT_MAP.values() for v in vals}, key=len, reverse=True)),
    re.IGNORECASE)

# ---------------- HTTP / lesing ----------------
def hent_html(url):
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.text

def hent_fil_data(url):
    r = requests.get(url, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    return r.headers.get("content-type", "").lower(), r.content

def les_pdf(data):
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return []
    lines = []
    for p in reader.pages:
        try:
            t = p.extract_text()
        except Exception:
            t = None
        if t:
            for ln in t.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(ln)
    return lines

def les_docx(data):
    try:
        doc = Document(BytesIO(data))
    except Exception:
        return []
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

# ---------------- hjelpefunksjoner dato/uke ----------------
def try_parse_date_str(s):
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        try: return date(y, mo, d)
        except: return None
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$", s)
    if m:
        d, mo, yy = int(m[1]), int(m[2]), int(m[3])
        if yy < 100: yy += 2000
        try: return date(yy, mo, d)
        except: return None
    m = re.match(r"^(\d{1,2})[./](\d{1,2})$", s)
    if m:
        d, mo = int(m[1]), int(m[2])
        if not (1 <= mo <= 12 and 1 <= d <= 31): return None
        y = date.today().year
        try: return date(y, mo, d)
        except: return None
    return None

def date_from_week_and_weekday(year_guess, uke_nummer, weekday_index):
    for y in (year_guess, year_guess-1, year_guess+1):
        try:
            return date.fromisocalendar(y, uke_nummer, weekday_index)
        except: pass
    return None

# ---------------- finn uke og filer ----------------
def finn_uke_lenker(soup):
    funn = []
    for a in soup.find_all("a", href=True):
        tekst = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"]
        m = re.search(r"uke\s*(\d{1,2})", tekst)
        if not m:
            m2 = re.search(r"uke[-_/ ]?(\d{1,2})", href.lower())
            if m2:
                m = m2
        if m:
            uke = int(m.group(1))
            url = href
            if url.startswith("/"):
                url = BASE_URL + url
            funn.append((uke, url))
    unique = {}
    for uke, url in funn:
        if uke not in unique:
            unique[uke] = url
    return [(u, unique[u]) for u in unique]

def velg_uke_auto(uke_lenker):
    cur = date.today().isocalendar()[1]
    for uke, url in uke_lenker:
        if uke == cur:
            return uke, url
    return min(uke_lenker, key=lambda x: abs(x[0] - cur))

def finn_filer_paa_uke_siden(soup):
    filer = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_l = href.lower()
        if "/api/rest/filer/" in href_l or any(href_l.endswith(ext) for ext in [".pdf", ".doc", ".docx", ".docm"]):
            url = href
            if url.startswith("/"):
                url = BASE_URL + url
            if url not in filer:
                filer.append(url)
    return filer

def finn_best_match_for_klasse(filer, klasse):
    for url in filer:
        ul = url.lower()
        for pat in KLASSE_MØNSTER_URL:
            if re.search(pat, ul):
                ctype, data = hent_fil_data(url)
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    lines = les_pdf(data)
                else:
                    lines = les_docx(data)
                return url, lines
    for url in filer:
        ctype, data = hent_fil_data(url)
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            lines = les_pdf(data)
        else:
            lines = les_docx(data)
        if lines and dokument_inneholder_klasse(lines):
            return url, lines
    return None, None

def dokument_inneholder_klasse(lines):
    blob = " ".join(lines).lower()
    for pat in KLASSE_MØNSTER_URL:
        if re.search(pat, blob):
            return True
    return False

# ---------------- parsing og sammenslåing ----------------
def should_join(current, nxt):
    nxts = nxt.strip()
    if not nxts:
        return False
    if nxts[0].islower():
        return True
    if not re.search(r"[.?!:]$", current) and not nxts[0].isupper():
        return True
    if len(nxts.split()) < 6 and not re.search(r"[.:?!]$", current):
        return True
    return False

def join_broken_lines(lines):
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        while ln.endswith("-") and i+1 < len(lines):
            ln = ln[:-1] + lines[i+1].strip()
            i += 1
        while i+1 < len(lines) and should_join(ln, lines[i+1]):
            ln = ln + " " + lines[i+1].strip()
            i += 1
        out.append(ln)
        i += 1
    return out

def split_into_day_blocks(lines):
    blocks = []
    started = False
    current_day = None
    buf = []
    for ln in lines:
        low = ln.lower()
        if not started:
            if "dag fag lekser" in low:
                started = True
            continue
        found_day = None
        for navn in UKEDAGER.keys():
            if navn in low:
                found_day = navn
                break
        if found_day:
            if buf:
                blocks.append((current_day, " ".join(buf).strip()))
                buf = []
            current_day = found_day.capitalize()
            remainder = re.sub(r".*\b" + re.escape(found_day) + r"\b", "", low, count=1).strip()
            if remainder:
                buf.append(remainder)
            continue
        buf.append(ln)
    if buf:
        blocks.append((current_day, " ".join(buf).strip()))
    return blocks

def split_block_into_tasks(block_text):
    toks = []
    split_positions = []
    for m in re.finditer(r"|".join([re.escape(k) for k in STIKKORD]) , block_text, flags=re.IGNORECASE):
        split_positions.append(m.start())
    for m in PAGE_REF_RE.finditer(block_text):
        split_positions.append(m.start())
    for m in TASK_REF_RE.finditer(block_text):
        split_positions.append(m.start())
    for m in re.finditer(r"\btil neste\b|\bi timen\b|\bfremføring\b", block_text, flags=re.IGNORECASE):
        split_positions.append(m.start())
    # also split on subject occurrences
    for m in SUBJECT_RE.finditer(block_text):
        split_positions.append(m.start())
    if not split_positions:
        return [block_text.strip()] if block_text.strip() else []
    split_positions = sorted(set(split_positions))
    last = 0
    for pos in split_positions:
        if pos - last > 40:
            seg = block_text[last:pos].strip()
            if seg:
                toks.append(seg)
            last = pos
    rem = block_text[last:].strip()
    if rem:
        toks.append(rem)
    if not toks:
        return [block_text.strip()]
    merged = []
    i = 0
    while i < len(toks):
        t = toks[i].strip()
        if len(t.split()) < 4 and i+1 < len(toks):
            toks[i+1] = (t + " " + toks[i+1]).strip()
        else:
            merged.append(t)
        i += 1
    # further split each merged segment by subject headers if multiple subjects present
    final = []
    for seg in merged:
        final.extend(split_by_subjects(seg))
    return final

def split_by_subjects(text):
    # find subject occurrences and split so each part starts with a subject if possible
    matches = list(SUBJECT_RE.finditer(text))
    if not matches:
        return [text.strip()]
    parts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        part = text[start:end].strip()
        parts.append(part)
    return [p for p in parts if p]

def extract_page_or_task_ref(text):
    m = PAGE_REF_RE.search(text)
    if m:
        if m.group(2):
            return f"side {m.group(1)}-{m.group(2)}"
        return f"side {m.group(1)}"
    m2 = TASK_REF_RE.search(text)
    if m2:
        return f"oppgave {m2.group(1)}"
    return None

def find_subject_in_text(text):
    # return normalized subject key or None
    low = text.lower()
    for key, variants in SUBJECT_MAP.items():
        for v in variants:
            if re.search(r"\b" + re.escape(v) + r"\b", low):
                return key
    # also try subject regex
    m = SUBJECT_RE.search(text)
    if m:
        found = m.group(0).lower()
        for key, variants in SUBJECT_MAP.items():
            if found in [v.lower() for v in variants]:
                return key
    return None

# ---------------- prosessering av blokk til oppgaver ----------------
def prosesser_block(block_day, block_text, uke_nummer):
    tasks = []
    year_guess = date.today().year
    dt = None
    # find explicit date tokens
    for tok in DATE_TOKEN_RE.findall(block_text):
        parsed = try_parse_date_str(tok)
        if parsed:
            dt = parsed
            break
    if block_day:
        idx = UKEDAGER.get(block_day.lower(), None)
        if idx:
            computed = date_from_week_and_weekday(year_guess, uke_nummer, idx)
            if computed:
                dt = computed
    segments = split_block_into_tasks(block_text)
    for seg in segments:
        seg_low = seg.lower()
        if any(k in seg_low for k in STIKKORD) or PAGE_REF_RE.search(seg) or TASK_REF_RE.search(seg) or SUBJECT_RE.search(seg):
            page_task = extract_page_or_task_ref(seg)
            tdate = dt.isoformat() if isinstance(dt, date) else None
            weekday = block_day
            subj = find_subject_in_text(seg)
            tasks.append({
                "tekst": seg.strip(),
                "dato": tdate,
                "ukedag": weekday,
                "side_eller_oppgave": page_task,
                "fag": subj
            })
    return tasks

# ---------------- hovedflyt ----------------
def main():
    print("Starter. Henter index.")
    index_html = hent_html(START_URL)
    index_soup = BeautifulSoup(index_html, "html.parser")

    uke_lenker = finn_uke_lenker(index_soup)
    if not uke_lenker:
        raise RuntimeError("Ingen uke-lenker funnet")

    uke_nummer, uke_url = velg_uke_auto(uke_lenker)
    print("Valgt uke:", uke_nummer, "URL:", uke_url)

    uke_html = hent_html(uke_url)
    uke_soup = BeautifulSoup(uke_html, "html.parser")

    filer = finn_filer_paa_uke_siden(uke_soup)
    if not filer:
        raise RuntimeError("Ingen filer funnet på uke-siden")

    print("Filer funnet:", len(filer))
    for f in filer:
        print(" -", f)

    fil_url, raw_lines = finn_best_match_for_klasse(filer, KLASSE)
    if not fil_url:
        raise RuntimeError("Fant ingen fil for klasse " + KLASSE)
    print("Valgt fil:", fil_url)

    merged = join_broken_lines(raw_lines)
    blocks = split_into_day_blocks(merged)

    all_tasks = []
    candidates = []
    for day, block_text in blocks:
        segs = split_block_into_tasks(block_text)
        for s in segs:
            if any(k in s.lower() for k in STIKKORD) or PAGE_REF_RE.search(s) or TASK_REF_RE.search(s) or SUBJECT_RE.search(s):
                candidates.append({"day": day, "text": s.strip()})
        tasks = prosesser_block(day, block_text, uke_nummer)
        all_tasks.extend(tasks)

    lekser = [t for t in all_tasks if any(k in t["tekst"].lower() for k in ["lekse", "innlever", "assignment", "les", "practice"])]
    prover = [t for t in all_tasks if any(k in t["tekst"].lower() for k in ["prøve", "test"])]

    output = {
        "uke": uke_nummer,
        "klasse": KLASSE,
        "kilde": fil_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    matched_texts = set(t["tekst"] for t in all_tasks)
    unmatched = [c for c in candidates if c["text"] not in matched_texts]

    debug = {
        "raw_lines": raw_lines,
        "merged_lines": merged,
        "blocks": [{"day": d, "text": txt} for d, txt in blocks],
        "candidates": candidates,
        "matched_count": len(all_tasks),
        "unmatched_candidates": unmatched,
        "extracted_tasks": all_tasks
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        json.dump(debug, f, ensure_ascii=False, indent=2)

    print("Ferdig. Funnet oppgaver:", len(all_tasks))
    print("Lekser:", len(lekser), "Prøver:", len(prover))
    print("Debug lagret i", DEBUG_FILE)
    print("Resultat lagret i", OUT_FILE)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FEILET:", e)
        raise
