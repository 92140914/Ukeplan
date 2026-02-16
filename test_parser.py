#!/usr/bin/env python3
"""
Testscript for debugging av parsing-funksjoner.
Bruker en eksempel-tekst i stedet for å hente fra nettet.
"""

import json
from fetch_8E_plan import (
    extract_pages_and_tasks,
    extract_info_by_category,
    parse_by_subject,
)

# Eksempel på tekst fra en ukeplan
EXAMPLE_TEXT = """
ARBEIDSPLAN for 8E Uke 7

MANDAG 10. februar
Norsk (1. og 2. time):
Vi jobber med sakprosa denne uken. Les teksten på s. 45-48.
Lekse: Gjør oppgave 3.1-3.5 som forberedelse til timen.

Matematikk (3. og 4. time):
Kapittel 4: Geometri
Lekse hjemme: Gjør oppgavene s. 218-220, oppgave 1.14-1.24
VIKTIG: Prøve på fredag over kapittel 3-4!

TIRSDAG 11. februar
Engelsk (1. og 2. time):
Grammar: Present Perfect
Lekse: Read chapter 5 in the textbook, page 85
Vocabulary test on Thursday - prepare vocabulary list

Naturfag (3. time):
Planeter i solsystemet
Les s. 142-145
Presentasjon fredag: Velg en planet og forbered en kort presentasjon (5 min)

ONSDAG 12. februar
Samfunnsfag (1. time):
Den franske revolusjonen
Les s. 98-102 og se video på Classroom

Kroppsøving (2.-4. time):
Lagidrett - innendørs

TORSDAG 13. februar
Norsk (1. time):
Fortsettelse sakprosa
Leselogg: Husk å føre leselogg hver dag!

Engelsk (2. time):
Gloseprøve - vocabulary fra side 85

Matematikk (3. time):
Repetisjonstime før prøven

KRLE (4. time):
Verdensreligioner

FREDAG 14. februar
Matematikk (1.-2. time):
Prøve: Kapittel 3 og 4 (Geometri)

Naturfag (3. time):
Presentasjoner om planeter - innlevering

Musikk (4. time):
Rytmiske øvelser
"""

def test_extract_pages_and_tasks():
    """Test utpakking av sidetall og oppgaver."""
    print("=" * 60)
    print("TEST: extract_pages_and_tasks()")
    print("=" * 60)
    
    pages, tasks = extract_pages_and_tasks(EXAMPLE_TEXT)
    
    print(f"\n📄 Sidetall funnet ({len(pages)}):")
    for page in pages:
        print(f"  - {page}")
    
    print(f"\n✍️ Oppgaver funnet ({len(tasks)}):")
    for task in tasks:
        print(f"  - {task}")
    
    return pages, tasks


def test_extract_info_by_category():
    """Test kategorisering av informasjon."""
    print("\n" + "=" * 60)
    print("TEST: extract_info_by_category()")
    print("=" * 60)
    
    info = extract_info_by_category(EXAMPLE_TEXT)
    
    for category, items in info.items():
        print(f"\n📌 {category.upper()} ({len(items)} element):")
        for i, item in enumerate(items, 1):
            print(f"\n  {i}. {item['beskrivelse'][:80]}...")
            if item['sidetall']:
                print(f"     Sidetall: {', '.join(item['sidetall'])}")
            if item['oppgaver']:
                print(f"     Oppgaver: {', '.join(item['oppgaver'])}")
    
    return info


def test_parse_by_subject():
    """Test parsing etter fag."""
    print("\n" + "=" * 60)
    print("TEST: parse_by_subject()")
    print("=" * 60)
    
    subjects = parse_by_subject(EXAMPLE_TEXT)
    
    for subject, data in subjects.items():
        print(f"\n📚 {subject.upper()}:")
        print(f"  Innhold: {data['innhold'][:100]}...")
        if data['sidetall']:
            print(f"  Sidetall: {', '.join(data['sidetall'])}")
        if data['oppgaver']:
            print(f"  Oppgaver: {', '.join(data['oppgaver'])}")
    
    return subjects


def test_full_parsing():
    """Test full parsing og JSON-generering."""
    print("\n" + "=" * 60)
    print("TEST: Full parsing")
    print("=" * 60)
    
    info = extract_info_by_category(EXAMPLE_TEXT)
    subjects = parse_by_subject(EXAMPLE_TEXT)
    
    result = {
        'uke': 7,
        'år': 2026,
        'klasse': '8E',
        'fag': subjects,
        'kategorier': info,
        'rå_tekst': EXAMPLE_TEXT[:500],
    }
    
    print("\n📋 Generert JSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # Lagre til fil
    with open('test_output.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("\n✅ Lagret til test_output.json")
    
    return result


def main():
    """Kjør alle tester."""
    print("\n🧪 TESTSCRIPT FOR UKEPLAN-PARSER")
    print("=" * 60)
    
    # Kjør tester
    test_extract_pages_and_tasks()
    test_extract_info_by_category()
    test_parse_by_subject()
    test_full_parsing()
    
    print("\n" + "=" * 60)
    print("✅ Alle tester fullført!")
    print("=" * 60)


if __name__ == "__main__":
    main()
