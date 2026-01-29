#!/usr/bin/env python3
import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import date, datetime

from PyPDF2 import PdfReader
from docx import Document

# ------------------ KONFIG ------------------
BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
UTDATA_FIL = "ukeplan-8E.json"
DEFAULT_KLASSE = "8E"

STIKKORD = [
    "lekse", "innlevering", "prøve", "test", "presentasjon", "framføring",
    "øvelse", "øving", "assignment", "lesson", "classroom", "les", "presentere",
    "presentation", "video", "practice", "øve"
]

KLASSE_MØNSTER_URL = [
    r"\b8e\b", r"\b8\.?e\b", r"\b8\s*e\b", r"8e[-_ ]", r"8e.*uke",
    r"8e.*\d{1,2}", r"8e\s*-\s*uke", r"klasse\s*8e", r"8e_uk[e]?", r"8e\.pdf",
    r"pdf8e", r".*8e.*"
]

UKEDAGER = {
    "mandag": 1, "tirsdag": 2, "onsdag": 3, "torsdag": 4,
    "fredag": 5, "lørdag": 6, "lordag": 6, "søndag": 7, "sondag": 7
}

REQ_TIMEOUT = 25

# ------------------ HJELPEFUNKSJONER ------------------
def hent_html(url):
    resp = requests.get(url, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    return resp.text

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
    current_week = date.today().isocalendar()[1]
    for uke, url in uke_lenker:
        if uke == current_week:
            return uke, url
    return min(uke_lenker, key=lambda x: abs(x[0] - current_week))

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

def hent_fil_data(url):
    resp = requests.get(url, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "").lower()
    return ctype, resp.content

def les_pdf(data):
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return []
    linjer = []
    for side in reader.pages:
        txt = side.extract_text()
        if txt:
            for line in txt.splitlines():
                if line.strip():
                    linjer.append(line.strip())
    return linjer

def les_docx(data):
    try:
        doc = Document(BytesIO(data))
    except Exception:
        return []
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

def try_parse_date_str(s):
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except: return None
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$", s)
    if m:
        d, mo, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yy < 100: yy += 2000
        try: return date(yy, mo, d)
        except: return None
    m = re.match(r"^(\d{1,2})[./](\d{1,2})$", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        if not (1 <= mo <= 12 and 1 <= d <= 31): return None
        y = date.today().year
        try: return date(y, mo, d)
        except: return None
    return None

def date_from_week_and_weekday(year_guess, uke_nummer, weekday_index):
    for y in (year_guess, year_guess-1, year_guess+1):
        try:
            dt = date.fromisocalendar(y, uke_nummer, weekday_index)
            return dt
        except:
            continue
    return None

def dokument_inneholder_klasse(linjer):
    samlet = " ".join(linjer).lower()
    for pat in KLASSE_MØNSTER_URL:
        if re.search(pat, samlet):
            return True
    return False

def finn_best_match_for_klasse(filer, klasse):
    for url in filer:
        url_lav = url.lower()
        for pat in KLASSE_MØNSTER_URL:
            if re.search(pat, url_lav):
                ctype, data = hent_fil_data(url)
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    linjer = les_pdf(data)
                else:
                    linjer = les_docx(data)
                return url, linjer
    for url in filer:
        ctype, data = hent_fil_data(url)
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            linjer = les_pdf(data)
        else:
            linjer = les_docx(data)
        if linjer and dokument_inneholder_klasse(linjer):
            return url, linjer
    return None, None

# ------------------ EKSTRAHERING ------------------
def ekstraher_oppgaver_med_dato_og_stikkord(linjer, uke_nummer):
    oppgaver = []
    current_date = None
    current_weekday_name = None
    date_token_re = re.compile(r"(\d{1,4}[./-]\d{1,4}(?:[./-]\d{2,4})?)")
    year_guess = date.today().year
    started = False

    for linje in linjer:
        lav = linje.lower().strip()
        if not started:
            if "dag fag lekser" in lav:
                started = True
            continue

        # Finn ukedag
        found_weekday = None
        for navn, idx in UKEDAGER.items():
            if navn in lav:
                found_weekday = (navn, idx)
                break
        if found_weekday:
            navn, idx = found_weekday
            dt = date_from_week_and_weekday(year_guess, uke_nummer, idx)
            if dt:
                current_date = dt
                current_weekday_name = navn.capitalize()
            else:
                current_date = None
                current_weekday_name = navn.capitalize()

        # Finn dato
        for tok in date_token_re.findall(linje):
            parsed = try_parse_date_str(tok)
            if parsed:
                current_date = parsed
                current_weekday_name = parsed.strftime("%A").capitalize()
                break

        # Sjekk stikkord
        if any(k in lav for k in STIKKORD):
            dato_str = current_date.isoformat() if isinstance(current_date, date) else None
            sidetall = None
            m = re.search(r"(side|oppgave|task)\s*(\d+)", lav)
            if m: sidetall = m.group(0)
            oppgaver.append({
                "tekst": linje.strip(),
                "dato": dato_str,
                "ukedag": current_weekday_name,
                "side_eller_oppgave": sidetall
            })
    return oppgaver

# ------------------ MAIN ------------------
def main():
    print("Starter fetch for klasse", DEFAULT_KLASSE)
    index_html = hent_html(START_URL)
    index_soup = BeautifulSoup(index_html, "html.parser")

    uke_lenker = finn_uke_lenker(index_soup)
    if not uke_lenker:
        raise RuntimeError("Fant ingen uke-lenker")

    uke_nummer, uke_url = velg_uke_auto(uke_lenker)
    print("Valgt uke:", uke_nummer, "URL:", uke_url)

    uke_html = hent_html(uke_url)
    uke_soup = BeautifulSoup(uke_html, "html.parser")

    filer = finn_filer_paa_uke_siden(uke_soup)
    if not filer:
        raise RuntimeError("Fant ingen filer på uke-siden")
    print("Filer funnet:", len(filer))

    fil_url, linjer = finn_best_match_for_klasse(filer, DEFAULT_KLASSE)
    if not fil_url:
        raise RuntimeError("Fant ingen fil for klasse " + DEFAULT_KLASSE)
    print("Valgt fil:", fil_url)

    if linjer is None or not linjer:
        ctype, data = hent_fil_data(fil_url)
        if "pdf" in ctype or fil_url.lower().endswith(".pdf"):
            linjer = les_pdf(data)
        else:
            linjer = les_docx(data)

    oppgaver = ekstraher_oppgaver_med_dato_og_stikkord(linjer, uke_nummer)

    lekser = [o for o in oppgaver if any(k in o["tekst"].lower() for k in ["lekse", "innlever", "assignment", "lesson", "les"])]
    prover = [o for o in oppgaver if any(k in o["tekst"].lower() for k in ["prøve", "test"])]

    resultat = {
        "uke": uke_nummer,
        "klasse": DEFAULT_KLASSE,
        "kilde": fil_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(UTDATA_FIL, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)

    print("Ferdig. JSON skrevet til", UTDATA_FIL)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Feilet:", e)
        raise
