#!/usr/bin/env python3
"""
GitHub Actions script for å hente ukeplan for klasse 8E fra Mjølkeråen skole.
Scriptet henter arbeidsplanen for den gjeldende uken, parser innholdet,
og lagrer strukturert informasjon i JSON-format.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import PyPDF2
import io

# Konfigurasjon
BASE_URL = "https://www.bergen.kommune.no"
ARBEIDSPLANER_URL = f"{BASE_URL}/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUTPUT_FILE = "ukeplan-8E.json"

# Stikkord for å identifisere klasse 8E (case-insensitive)
KLASSE_KEYWORDS = [
    r'8\s*[EeéÉ]',  # Matcher "8E", "8 E", "8e", etc.
    r'8[EeéÉ]',
    r'åtte\s*[EeéÉ]',
]

# Stikkord for å identifisere viktig informasjon
INFO_KEYWORDS = {
    'lekser': [r'lekse[rn]?', r'hjemmearbeid', r'homework'],
    'prøver': [r'prøve[rn]?', r'test[en]?', r'eksamen'],
    'gloseprøver': [r'glose\s*prøve[rn]?', r'ordprøve[rn]?'],
    'presentasjoner': [r'presentasjon[en]?', r'fremføring[en]?', r'innlevering[en]?'],
    'leselogg': [r'lese\s*logg', r'lesing'],
    'innleveringer': [r'innlevering[en]?', r'frist[en]?'],
}

# Regex for sidetall og oppgaver
PAGE_PATTERNS = [
    r's\.?\s*(\d+)\s*-\s*(\d+)',  # s. 218-220
    r's\.?\s*(\d+)',  # s. 218
    r'side[rn]?\s*(\d+)\s*-\s*(\d+)',  # side 218-220
    r'side[rn]?\s*(\d+)',  # side 218
]

TASK_PATTERNS = [
    r'oppgave[rn]?\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',  # oppgave 1.14-1.24
    r'oppgave[rn]?\s*(\d+\.?\d*)',  # oppgave 1.14
    r'oppg\.?\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',  # oppg. 1.14-1.24
    r'oppg\.?\s*(\d+\.?\d*)',  # oppg. 1.14
]


def get_week_number():
    """Finn gjeldende ukenummer."""
    today = datetime.now()
    week_num = today.isocalendar()[1]
    year = today.year
    return week_num, year


def find_week_url(week_num, year):
    """
    Finn URL til arbeidsplansiden for den gjeldende uken.
    Prøver flere varianter av URL-format.
    """
    possible_urls = [
        f"{ARBEIDSPLANER_URL}/uke-{week_num}-{year}",
        f"{ARBEIDSPLANER_URL}/uke{week_num}-{year}",
        f"{ARBEIDSPLANER_URL}/uke-{week_num}",
    ]
    
    for url in possible_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"✓ Fant ukeside: {url}")
                return url
        except requests.RequestException:
            continue
    
    return None


def find_8e_file_link(html_content):
    """
    Søk gjennom HTML for å finne lenke til PDF/DOC for klasse 8E.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Søk etter alle lenker
    all_links = soup.find_all('a', href=True)
    
    for link in all_links:
        link_text = link.get_text().strip()
        link_href = link['href']
        
        # Sjekk om lenketeksten eller href matcher 8E-stikkord
        for pattern in KLASSE_KEYWORDS:
            if re.search(pattern, link_text, re.IGNORECASE):
                # Sørg for at vi har full URL
                if not link_href.startswith('http'):
                    link_href = BASE_URL + link_href
                print(f"✓ Fant 8E-lenke: {link_text} -> {link_href}")
                return link_href
    
    # Hvis ingen direkte match, søk etter generiske "8. trinn" lenker
    for link in all_links:
        link_text = link.get_text().strip()
        link_href = link['href']
        
        if re.search(r'8\.?\s*trinn', link_text, re.IGNORECASE):
            if not link_href.startswith('http'):
                link_href = BASE_URL + link_href
            print(f"✓ Fant 8. trinn lenke: {link_text} -> {link_href}")
            return link_href
    
    return None


def download_file(url):
    """Last ned fil fra URL."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        print(f"✗ Feil ved nedlasting av fil: {e}")
        return None


def extract_text_from_pdf(pdf_content):
    """Ekstraher tekst fra PDF."""
    try:
        pdf_file = io.BytesIO(pdf_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return text
    except Exception as e:
        print(f"✗ Feil ved parsing av PDF: {e}")
        return None


def extract_pages_and_tasks(text):
    """Ekstraher sidetall og oppgavenumre fra tekst."""
    pages = []
    tasks = []
    
    # Søk etter sidetall
    for pattern in PAGE_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                pages.append(f"s. {match.group(1)}-{match.group(2)}")
            else:
                pages.append(f"s. {match.group(1)}")
    
    # Søk etter oppgaver
    for pattern in TASK_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 2:
                tasks.append(f"oppgave {match.group(1)}-{match.group(2)}")
            else:
                tasks.append(f"oppgave {match.group(1)}")
    
    return pages, tasks


def extract_info_by_category(text):
    """Ekstraher informasjon kategorisert etter type."""
    structured_info = {}
    
    # Del opp teksten i linjer
    lines = text.split('\n')
    
    for category, keywords in INFO_KEYWORDS.items():
        category_items = []
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Sjekk om linjen inneholder et stikkord for denne kategorien
            for keyword in keywords:
                if re.search(keyword, line_lower):
                    # Ta med linjen og neste linjer som kan inneholde detaljer
                    context_lines = [line]
                    
                    # Se på neste par linjer for å få kontekst
                    for j in range(1, min(4, len(lines) - i)):
                        next_line = lines[i + j].strip()
                        if next_line and len(next_line) > 5:
                            context_lines.append(next_line)
                        else:
                            break
                    
                    item_text = ' '.join(context_lines).strip()
                    
                    # Ekstraher sidetall og oppgaver
                    pages, tasks = extract_pages_and_tasks(item_text)
                    
                    item = {
                        'beskrivelse': item_text[:200],  # Begrens lengde
                        'sidetall': pages,
                        'oppgaver': tasks,
                    }
                    
                    category_items.append(item)
                    break
        
        if category_items:
            structured_info[category] = category_items
    
    return structured_info


def parse_by_subject(text):
    """
    Parser teksten og organiserer etter fag.
    Norsk, Matte, Engelsk, osv.
    """
    # Vanlige fagnavn
    subjects = ['norsk', 'matematikk', 'matte', 'engelsk', 'naturfag', 
                'samfunnsfag', 'krle', 'kunst', 'musikk', 'mat og helse', 
                'kroppsøving', 'spansk', 'tysk', 'fransk']
    
    subject_pattern = '|'.join(subjects)
    subject_data = {}
    
    # Del tekst i seksjoner basert på fagnavn
    lines = text.split('\n')
    current_subject = None
    current_content = []
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Sjekk om linjen starter en ny fagseksjon
        matched_subject = None
        for subject in subjects:
            if re.search(rf'\b{subject}\b', line_lower):
                matched_subject = subject
                break
        
        if matched_subject:
            # Lagre forrige fagseksjon
            if current_subject and current_content:
                content_text = '\n'.join(current_content)
                pages, tasks = extract_pages_and_tasks(content_text)
                subject_data[current_subject] = {
                    'innhold': content_text.strip(),
                    'sidetall': pages,
                    'oppgaver': tasks,
                }
            
            # Start ny fagseksjon
            current_subject = matched_subject
            current_content = [line]
        elif current_subject:
            current_content.append(line)
    
    # Lagre siste fagseksjon
    if current_subject and current_content:
        content_text = '\n'.join(current_content)
        pages, tasks = extract_pages_and_tasks(content_text)
        subject_data[current_subject] = {
            'innhold': content_text.strip(),
            'sidetall': pages,
            'oppgaver': tasks,
        }
    
    return subject_data


def parse_plan(content, file_url):
    """
    Parser ukeplanen og ekstraher strukturert informasjon.
    """
    # Ekstraher tekst fra PDF
    text = extract_text_from_pdf(content)
    
    if not text:
        print("✗ Kunne ikke ekstrahere tekst fra PDF")
        return None
    
    print(f"✓ Ekstraherte {len(text)} tegn fra PDF")
    
    # Parser informasjon
    info_by_category = extract_info_by_category(text)
    subject_data = parse_by_subject(text)
    
    # Bygg strukturert output
    week_num, year = get_week_number()
    
    result = {
        'uke': week_num,
        'år': year,
        'klasse': '8E',
        'hentet_dato': datetime.now().isoformat(),
        'kilde_url': file_url,
        'fag': subject_data,
        'kategorier': info_by_category,
        'rå_tekst': text[:1000],  # Første 1000 tegn for debugging
    }
    
    return result


def save_json(data, filename):
    """Lagre data til JSON-fil."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ Lagret data til {filename}")
        return True
    except Exception as e:
        print(f"✗ Feil ved lagring av JSON: {e}")
        return False


def main():
    """Hovedfunksjon."""
    print("=" * 60)
    print("Henter ukeplan for klasse 8E fra Mjølkeråen skole")
    print("=" * 60)
    
    # Finn gjeldende uke
    week_num, year = get_week_number()
    print(f"\n📅 Gjeldende uke: {week_num}, år: {year}")
    
    # Finn URL til ukesiden
    print(f"\n🔍 Søker etter arbeidsplanside...")
    week_url = find_week_url(week_num, year)
    
    if not week_url:
        print(f"✗ Kunne ikke finne arbeidsplanside for uke {week_num}")
        sys.exit(1)
    
    # Hent ukesiden
    print(f"\n📥 Henter innhold fra {week_url}...")
    try:
        response = requests.get(week_url, timeout=10)
        response.raise_for_status()
        html_content = response.text
    except requests.RequestException as e:
        print(f"✗ Feil ved henting av ukeside: {e}")
        sys.exit(1)
    
    # Finn lenke til 8E-fil
    print(f"\n🔍 Søker etter 8E-fil...")
    file_url = find_8e_file_link(html_content)
    
    if not file_url:
        print("✗ Kunne ikke finne fil for klasse 8E")
        sys.exit(1)
    
    # Last ned filen
    print(f"\n📥 Laster ned {file_url}...")
    file_content = download_file(file_url)
    
    if not file_content:
        print("✗ Kunne ikke laste ned fil")
        sys.exit(1)
    
    print(f"✓ Lastet ned {len(file_content)} bytes")
    
    # Parser filen
    print(f"\n📊 Parser ukeplan...")
    parsed_data = parse_plan(file_content, file_url)
    
    if not parsed_data:
        print("✗ Kunne ikke parse ukeplan")
        sys.exit(1)
    
    # Vis sammendrag
    print(f"\n📋 Sammendrag:")
    print(f"  - Fag funnet: {len(parsed_data.get('fag', {}))}")
    print(f"  - Kategorier funnet: {len(parsed_data.get('kategorier', {}))}")
    
    if parsed_data.get('fag'):
        print(f"\n📚 Fag:")
        for subject in parsed_data['fag'].keys():
            print(f"  - {subject.capitalize()}")
    
    if parsed_data.get('kategorier'):
        print(f"\n📌 Viktig informasjon:")
        for category, items in parsed_data['kategorier'].items():
            print(f"  - {category.capitalize()}: {len(items)} element(er)")
    
    # Lagre til JSON
    print(f"\n💾 Lagrer til {OUTPUT_FILE}...")
    if save_json(parsed_data, OUTPUT_FILE):
        print("\n✅ Fullført!")
        return 0
    else:
        print("\n✗ Feil ved lagring")
        return 1


if __name__ == "__main__":
    sys.exit(main())
