#!/usr/bin/env python3
import re
import json
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime

from PyPDF2 import PdfReader
from docx import Document

# Konfig
BASE_URL = "https://www.bergen.kommune.no"
START_URL = BASE_URL + "/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
UTDATA_FIL = "ukeplan-8E.json"
DEFAULT_KLASSE = "8E"

# Stikkord for å finne lekser og prøver
STIKKORD = ["lekse", "prøve", "innlevering", "presentasjon", "framføring", "øvelse", "øving"]

# Regex for klasse-identifikasjon i tekst
KLASSE_MØNSTER = [r"\b8\s*e\b", r"\b8e\b", r"klasse\s*8e", r"8\.?\s*e"]

# Timeout for requests
REQ_TIMEOUT = 25


def load_config():
    """
    Optional config.json support.
    If config.json exists, it may contain:
      { "uke": 5, "klasse": "8E" }
    uke null or missing -> auto nyeste uke
    klasse optional
    """
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
            uke = cfg.get("uke")
            klasse = cfg.get("klasse", DEFAULT_KLASSE)
            return uke, klasse
    except FileNotFoundError:
        return None, DEFAULT_KLASSE
    except Exception as e:
        print("Warning: failed to load config.json:", e)
        return None, DEFAULT_KLASSE


def hent_html(url):
    print("Henter HTML:", url)
    resp = requests.get(url, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def finn_uke_lenker(soup):
    """
    Finn alle lenker som ser ut som uke-lenker.
    Returnerer liste av (uke_nummer, url).
    Matcher både link-tekst og href-mønster.
    """
    funn = []
    for a in soup.find_all("a", href=True):
        tekst = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"]

        # Prøv å finne uke i tekst først
        m = re.search(r"uke\s*(\d{1,2})", tekst)
        if m:
            uke = int(m.group(1))
            url = href
            if url.startswith("/"):
                url = BASE_URL + url
            funn.append((uke, url))
            continue

        # Sjekk href for mønster
        href_l = href.lower()
        m2 = re.search(r"uke[-_/ ]?(\d{1,2})", href_l)
        if m2:
            uke = int(m2.group(1))
            url = href
            if url.startswith("/"):
                url = BASE_URL + url
            funn.append((uke, url))
            continue

    # Unike urler per uke, behold maks per uke
    unique = {}
    for uke, url in funn:
        if uke not in unique:
            unique[uke] = url
    result = [(u, unique[u]) for u in unique]
    return result


def velg_uke(uke_override, uke_lenker):
    """
    Hvis uke_override gitt, prøv finne den. Ellers velg høyeste uke.
    """
    if uke_override is not None:
        for u, url in uke_lenker:
            if u == int(uke_override):
                print("Bruker uke fra config:", u)
                return u, url
        raise RuntimeError(f"Konfigurert uke {uke_override} ikke funnet på index")
    if not uke_lenker:
        raise RuntimeError("Ingen uke-lenker funnet")
    uke_lenker.sort(key=lambda x: x[0], reverse=True)
    print("Valgt nyeste uke:", uke_lenker[0][0])
    return uke_lenker[0][0], uke_lenker[0][1]


def finn_filer_paa_uke_siden(soup):
    """
    Hent alle fil-URLer fra uke-siden.
    Mønstre:
      * href inneholder /api/rest/filer/
      * eller href slutter med .pdf .doc .docx
    Returnerer liste av fulle URLer.
    """
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
    print("Laster ned fil:", url)
    resp = requests.get(url, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "").lower()
    data = resp.content
    return ctype, data


def les_pdf(data):
    """
    Hent tekstlinjer fra PDF.
    Hvis PDF er skannet og mangler tekst, returnerer tom liste.
    """
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as e:
        print("PdfReader feilet:", e)
        return []
    linjer = []
    for side in reader.pages:
        try:
            txt = side.extract_text()
        except Exception:
            txt = None
        if txt:
            # split på newline for bedre linjehåndtering
            for line in txt.splitlines():
                if line.strip():
                    linjer.append(line.strip())
    return linjer


def les_docx(data):
    try:
        doc = Document(BytesIO(data))
    except Exception as e:
        print("Docx-lesing feilet:", e)
        return []
    linjer = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            linjer.append(t)
    return linjer


def dokument_inneholder_klasse(linjer, klasse_pattern_list):
    samlet = " ".join(linjer).lower()
    for pat in klasse_pattern_list:
        if re.search(pat, samlet):
            return True
    return False


def finn_best_match_for_klasse(filer, klasse):
    """
    Først sjekk href for '8e' eller 'pdf8e' i url.
    Hvis ikke funnet, last ned og sjekk innhold.
    Returnerer valgt fil-URL og tekstlinjer.
    """
    # Prioriter filer med klasse i url
    for url in filer:
        if klasse.lower().replace(" ", "") in url.lower().replace(" ", ""):
            try:
                ctype, data = hent_fil_data(url)
            except Exception as e:
                print("Feil ved nedlasting av prioritert fil:", e)
                continue

            if "pdf" in ctype or url.lower().endswith(".pdf"):
                linjer = les_pdf(data)
            else:
                linjer = les_docx(data)

            # Hvis fil har tekst eller klasse i url, aksepter den
            if linjer or klasse.lower() in url.lower():
                return url, linjer

    # Fallback: sjekk innhold i alle filer
    for url in filer:
        try:
            ctype, data = hent_fil_data(url)
        except Exception as e:
            print("Feil ved nedlasting fil:", e)
            continue

        if "pdf" in ctype or url.lower().endswith(".pdf"):
            linjer = les_pdf(data)
        else:
            linjer = les_docx(data)

        if not linjer:
            # Ingen tekst funnet i fil. Kan være skannet PDF.
            print("Ingen tekst funnet i fil:", url)
            continue

        if dokument_inneholder_klasse(linjer, KLASSE_MØNSTER):
            return url, linjer

    # Hvis ingen match
    return None, None


def ekstraher_oppgaver(linjer):
    """
    Gå gjennom linjer og finn linjer med stikkord.
    Returnerer liste av objekter med tekst og evt dato.
    """
    funn = []
    date_re = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")
    for linje in linjer:
        lav = linje.lower()
        if any(k in lav for k in STIKKORD):
            dato = None
            m = date_re.search(linje)
            if m:
                dato = m.group(1)
            funn.append({"tekst": linje.strip(), "dato": dato})
    return funn


def main():
    uke_override, klasse_from_cfg = load_config()
    klasse = klasse_from_cfg or DEFAULT_KLASSE
    print("Starter. Klasse:", klasse, "Uke overstyring:", uke_override)

    # Hent index
    index_html = hent_html(START_URL)
    index_soup = BeautifulSoup(index_html, "html.parser")

    uke_lenker = finn_uke_lenker(index_soup)
    if not uke_lenker:
        raise RuntimeError("Fant ingen uke-lenker på index")

    uke_nummer, uke_url = velg_uke(uke_override, uke_lenker)
    print("Går til uke-side:", uke_url)

    uke_html = hent_html(uke_url)
    uke_soup = BeautifulSoup(uke_html, "html.parser")

    filer = finn_filer_paa_uke_siden(uke_soup)
    print("Filer funnet på uke-siden:", len(filer))
    if not filer:
        raise RuntimeError("Fant ingen fil-lenker på uke-siden")

    valgt_url, linjer = finn_best_match_for_klasse(filer, klasse)
    if not valgt_url:
        raise RuntimeError("Fant ingen fil for klasse " + klasse)

    print("Valgt fil for klasse:", valgt_url)

    # Hvis linjer ikke allerede er lastet, last fil på nytt og hent linjer
    if linjer is None:
        ctype, data = hent_fil_data(valgt_url)
        if "pdf" in ctype or valgt_url.lower().endswith(".pdf"):
            linjer = les_pdf(data)
        else:
            linjer = les_docx(data)

    # Hvis fortsatt ingen tekst, varsle
    if not linjer:
        print("Valgt fil mangler tekst. Fil mulig skannet PDF. OCR nødvendig for å hente innhold.")
        # Lag tom JSON med kilde info
        resultat = {
            "uke": uke_nummer,
            "klasse": klasse,
            "kilde": valgt_url,
            "lekser": [],
            "prover": [],
            "warning": "fil har ingen utvinnbar tekst, OCR nødvendig"
        }
        with open(UTDATA_FIL, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print("Ferdig, skrev JSON med warning")
        return

    oppgaver = ekstraher_oppgaver(linjer)
    # Del oppgaver i lekser og prøver
    lekser = [o for o in oppgaver if any(k in o["tekst"].lower() for k in ["lekse", "innlevering"])]
    prover = [o for o in oppgaver if any(k in o["tekst"].lower() for k in ["prøve", "test"])]

    resultat = {
        "uke": uke_nummer,
        "klasse": klasse,
        "kilde": valgt_url,
        "lekser": lekser,
        "prover": prover,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(UTDATA_FIL, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)

    print("Ferdig. Skriver", UTDATA_FIL, "oppføringer lekser:", len(lekser), "prøver:", len(prover))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Feilet:", e)
        raise
