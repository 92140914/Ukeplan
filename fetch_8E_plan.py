#!/usr/bin/env python3
"""
fetch_8E_plan.py

Skript som besøker arbeidsplan-siden for Mjølkeraen skole, velger enten "Nåværende uke" (eller "Neste uke" hvis i søndag),
trykker på klasse-knappen/lenken for "8E", laster ned eventuelle PDF/planer, ekstraherer informasjon om lekser, prøver,
presentasjoner osv., og lagrer resultatet i ukeplan-8E.json.

Bruk (forutsetninger):
    pip install playwright requests PyPDF2 python-dateutil
    playwright install

Kjør:
    python fetch_8E_plan.py

Kommentarer:
- Scriptet bruker Playwright for å håndtere JavaScript-klikk og dynamisk innhold.
- For å finne elementer bruker vi "stikkord"/tekst-søk (f.eks. "Nåværende uke", "Neste uke", "8E").
- PDF-er blir lastet ned og analysert med PyPDF2. Vi leter etter nøkkelord som "lekse", "prøve", "presentasjon" osv.
- Resultatet er en JSON-fil med dato, side(pagenr) og tekstutdrag.

"""

import re
import os
import json
import tempfile
from datetime import datetime
from pathlib import Path

import requests
from dateutil import parser as dateparser
from PyPDF2 import PdfReader

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUTPUT_JSON = "ukeplan-8E.json"
KEYWORDS = [
    r"lekse",
    r"lekser",
    r"prøve",
    r"prøver",
    r"presentasjon",
    r"innlevering",
    r"præsentasjon",
    r"tentamen",
    r"vurdering",
]
KEYWORD_RE = re.compile("|".join(KEYWORDS), re.IGNORECASE)
DATE_PATTERNS = [
    r"\b(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{2,4})\b",  # dd.mm.yyyy
    r"\b(\d{1,2})[\.\-/](\d{1,2})\b",  # dd.mm
]

WEEKDAY_IS_SUNDAY = lambda: datetime.now().weekday() == 6  # Monday=0 ... Sunday=6


def try_parse_date(text):
    """Forsøk å finne en dato i en tekststreng. Returner ISO-dato hvis funnet, ellers None."""
    # Først: let etter eksplisitte dd.mm.yyyy eller dd.mm
    for pat in DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            try:
                # Bruk dateutil for robust parsing
                d = dateparser.parse(m.group(0), dayfirst=True, yearfirst=False)
                return d.date().isoformat()
            except Exception:
                continue
    # Neste: se etter ukedager + datolinjer (f.eks. "Mandag 9. februar")
    weekday_names = [
        "mandag",
        "tirsdag",
        "onsdag",
        "torsdag",
        "fredag",
        "lørdag",
        "søndag",
        "sondag",
    ]
    txt_low = text.lower()
    for wd in weekday_names:
        if wd in txt_low:
            # Prøv å hente en dato etter ukedag
            m = re.search(r"\b" + wd + r"[^\d]{0,10}(\d{1,2}[\.\-/]\d{1,2}(?:[\.\-/]\d{2,4})?)", txt_low)
            if m:
                try:
                    d = dateparser.parse(m.group(1), dayfirst=True)
                    return d.date().isoformat()
                except Exception:
                    pass
    return None


def extract_items_from_pdf(pdf_path):
    """Les PDF, gå gjennom hver side, og finn linjer som inneholder nøkkelord.
    Returner liste av funn med dato (hvis mulig), side og tekst.
    """
    items = []
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        print(f"Kunne ikke åpne PDF {pdf_path}: {e}")
        return items, 0

    num_pages = len(reader.pages)
    for i in range(num_pages):
        try:
            page = reader.pages[i]
            text = page.extract_text() or ""
        except Exception:
            text = ""
        # Del opp i linjer for enklere matching
        for line in text.splitlines():
            if KEYWORD_RE.search(line):
                date = try_parse_date(line)
                items.append({
                    "page": i + 1,
                    "text": line.strip(),
                    "date_found": date,
                })
    return items, num_pages


def download_url_to_file(url, dest_path):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)


def find_pdf_links_from_page(page):
    """Hent lenker som ser ut som PDF-er fra siden. Returnerer liste med absolute URLs."""
    anchors = page.query_selector_all("a")
    pdf_urls = []
    for a in anchors:
        href = a.get_attribute("href")
        if not href:
            continue
        href_low = href.lower()
        if href_low.endswith(".pdf") or ".pdf?" in href_low:
            pdf_urls.append(page.evaluate("(el) => el.href", a))
    # I tillegg: iframe eller embed som pekte på pdf
    frames = page.query_selector_all("iframe, embed")
    for f in frames:
        src = f.get_attribute("src")
        if src and ".pdf" in src.lower():
            # noen ganger er src relativ
            pdf_urls.append(page.evaluate("(el) => el.src", f))
    # Unik
    return list(dict.fromkeys(pdf_urls))


def click_by_text(locator_page, texts):
    """Forsøk å klikke et element som inneholder ett av tekstene i listen (stikkord).
    Tekstene forsøkes i gitt rekkefølge.
    Returnerer True hvis en klikk ble utført.
    """
    for t in texts:
        try:
            # Prøv flere måter: direkte tekst-locator, role=button, og CSS-selectors med :has-text
            locators = [
                f"text=/{t}/i",
                f"button:has-text(\"{t}\")",
                f"a:has-text(\"{t}\")",
            ]
            for sel in locators:
                el = locator_page.locator(sel)
                if el.count() > 0:
                    el.first.click()
                    return True
        except Exception:
            continue
    return False


def main():
    result = {
        "scrape_time": datetime.utcnow().isoformat() + "Z",
        "source": BASE_URL,
        "pdfs": [],
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE_URL, wait_until="networkidle")

        # Hvilken knapp skal vi trykke? Hvis i søndag -> trykk "Neste uke", ellers "Nåværende uke"
        if WEEKDAY_IS_SUNDAY():
            clicked = click_by_text(page, ["Neste uke", "Neste uke >", "Neste uke»"])
            if not clicked:
                print("Fant ikke 'Neste uke' - prøver 'Nåværende uke' som fallback")
                click_by_text(page, ["Nåværende uke", "Nåværende"])
        else:
            clicked = click_by_text(page, ["Nåværende uke", "Nåværende"])
            if not clicked:
                print("Fant ikke 'Nåværende uke' - prøver 'Neste uke' som fallback")
                click_by_text(page, ["Neste uke"]) 

        # Vent litt for at innhold skal oppdatere
        page.wait_for_timeout(1000)

        # Trykk på 8E (bruk stikkord-søk)
        # Noen sider kan vise "8 E" eller "8E" eller "8. E" - vi prøver flere varianter
        eight_variants = [r"\b8E\b", r"\b8\s?E\b", "8 E", "8E", "8. E"]
        clicked_8e = False
        for v in eight_variants:
            try:
                # tekst-locator med regex
                el = page.locator(f"text=/{v}/i")
                if el.count() > 0:
                    el.first.click()
                    clicked_8e = True
                    break
            except Exception:
                continue
        if not clicked_8e:
            print("Fant ikke klasse 8E via stikkord. Søker etter lenker som inneholder '8' og 'E'.")
            # fallback: søk etter lenker med begge tegn
            anchors = page.query_selector_all("a")
            for a in anchors:
                txt = (a.inner_text() or "").strip()
                if '8' in txt and ('E' in txt or 'e' in txt):
                    try:
                        a.click()
                        clicked_8e = True
                        break
                    except Exception:
                        pass

        page.wait_for_load_state("networkidle")

        # Finn PDF-lenker på denne siden
        pdf_urls = find_pdf_links_from_page(page)

        # Hvis ingen PDF-er funnet rett etter å ha klikket 8E, prøv å lete i hele siden (inkl. dynamisk innhold)
        if not pdf_urls:
            page.wait_for_timeout(1000)
            pdf_urls = find_pdf_links_from_page(page)

        # Hvis fortsatt ingen pdf, prøv å samle hrefs fra anchors og filtrer på 'ukeplan' eller '8E'
        if not pdf_urls:
            anchors = page.query_selector_all("a")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if '.pdf' in href.lower() or 'ukeplan' in href.lower() or '8e' in href.lower():
                    try:
                        abs_href = page.evaluate("(el) => el.href", a)
                        pdf_urls.append(abs_href)
                    except Exception:
                        continue

        # Last ned og prosesser hver pdf
        tmpdir = tempfile.mkdtemp(prefix="ukeplan_")
        for url in pdf_urls:
            try:
                fname = os.path.basename(url.split('?')[0]) or "plan.pdf"
                dest = os.path.join(tmpdir, fname)
                print(f"Laster ned {url} -> {dest}")
                download_url_to_file(url, dest)
                items, pages = extract_items_from_pdf(dest)
                result["pdfs"].append({
                    "url": url,
                    "filename": fname,
                    "local_path": dest,
                    "pages": pages,
                    "items": items,
                })
            except Exception as e:
                print(f"Feil ved behandling av {url}: {e}")

        # Hvis ingen pdf-er ble funnet, prøv å hente eventuelt embedded PDF URL fra viewer eller json
        if not result["pdfs"]:
            print("Ingen PDF-filer funnet. Eksporterer info om sideens HTML for manuell gjennomgang.")
            html_dump = os.path.join(tmpdir, "page.html")
            with open(html_dump, "w", encoding="utf-8") as f:
                f.write(page.content())
            result["page_html_dump"] = html_dump

        # Lukk nettleser
        context.close()
        browser.close()

    # Lagre til JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as jf:
        json.dump(result, jf, ensure_ascii=False, indent=2)

    print(f"Ferdig. Resultat lagret i {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
