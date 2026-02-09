#!/usr/bin/env python3
import re
import os
import json
import tempfile
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

BASE_URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUTPUT_JSON = "ukeplan-8E.json"
KEYWORDS = [
    "lekse", "lekser", "prøve", "prøver",
    "presentasjon", "innlevering", "tentamen", "vurdering"
]
KEYWORD_RE = re.compile("|".join(KEYWORDS), re.IGNORECASE)
DATE_PATTERNS = [
    r"\b(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{2,4})\b",  # dd.mm.yyyy
    r"\b(\d{1,2})[\.\-/](\d{1,2})\b",  # dd.mm
]

def try_parse_date(text):
    for pat in DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            parts = m.group(0).split(".")
            if len(parts) == 3:
                day, month, year = parts
            else:
                day, month = parts
                year = str(datetime.now().year)
            try:
                return datetime(int(year), int(month), int(day)).date().isoformat()
            except:
                continue
    return None

def extract_items_from_pdf(pdf_path):
    items = []
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        print(f"Kunne ikke åpne PDF {pdf_path}: {e}")
        return items, 0

    num_pages = len(reader.pages)
    for i in range(num_pages):
        page = reader.pages[i]
        text = page.extract_text() or ""
        for line in text.splitlines():
            if KEYWORD_RE.search(line):
                date = try_parse_date(line)
                items.append({
                    "page": i + 1,
                    "text": line.strip(),
                    "date_found": date
                })
    return items, num_pages

def main():
    result = {
        "scrape_time": datetime.utcnow().isoformat() + "Z",
        "source": BASE_URL,
        "pdfs": [],
    }

    resp = requests.get(BASE_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Finn alle lenker som peker på PDF og inneholder 8E eller ukeplan
    pdf_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf") or ".pdf?" in href.lower():
            if "8e" in href.lower() or "ukeplan" in href.lower():
                pdf_urls.append(urljoin(BASE_URL, href))

    tmpdir = tempfile.mkdtemp(prefix="ukeplan_")
    for url in pdf_urls:
        try:
            fname = os.path.basename(url.split("?")[0]) or "plan.pdf"
            dest = os.path.join(tmpdir, fname)
            print(f"Laster ned {url} -> {dest}")
            r = requests.get(url)
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)

            items, pages = extract_items_from_pdf(dest)
            result["pdfs"].append({
                "url": url,
                "filename": fname,
                "local_path": dest,
                "pages": pages,
                "items": items
            })
        except Exception as e:
            print(f"Feil ved behandling av {url}: {e}")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as jf:
        json.dump(result, jf, ensure_ascii=False, indent=2)

    print(f"Ferdig. Resultat lagret i {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
