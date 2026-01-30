import json
from datetime import datetime

INPUT_JSON = "input.json"
OUTPUT_JSON = "ukeplan-8E.json"

KEYWORDS = [
    "lekse","lekser","oppgave","innlevering","frist","lese","leseboken",
    "leseloggen","øve","øving","presentasjon","fremføring","prøve","prøver",
    "kapittelprøve","gloseprøve","gloseprøver","quiz","test","vurdering",
    "eksamen","samtale","classroom","digitaleoppgaver","video","film",
    "arbeid i boken","arbeid i heftet","oppgavesett","sidene","repetisjon",
    "forberedelse","prosjekt","innleveringsfrist","se i classroom"
]

UKEDAGER = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag"]

# Fast fag per dag
FAG_PER_DAG = {
    "Mandag": ["norsk","matte","engelsk","krle"],
    "Tirsdag": ["språk","matte","norsk"],
    "Onsdag": ["norsk","naturfag","matte"],
    "Torsdag": ["språk","samfunn","norsk","matte"],
    "Fredag": ["norsk","matte","spansk","tysk","fransk"]
}

def er_planleggingsdag(tekst):
    return "planleggingsdag" in tekst.lower()

def gyldig_lekse(tekst):
    t = tekst.lower()
    if len(t.strip()) < 5:
        return False
    if any(x in t for x in ["tlf","telefon","berg","kommune","marikollen"]):
        return False
    return any(k in t for k in KEYWORDS)

def finn_fag(tekst, dag):
    t = tekst.lower()
    for fag in FAG_PER_DAG.get(dag, []):
        if fag in t:
            return fag
    return None

def filtrer_lekser(data):
    resultat = []
    for l in data.get("lekser", []):
        tekst = l.get("tekst", "")
        dag = l.get("ukedag")
        if not dag:
            dag = "Mandag"  # fallback hvis ingen dag
        if er_planleggingsdag(tekst):
            continue
        if not gyldig_lekse(tekst):
            continue
        fag = finn_fag(tekst, dag)
        if not fag:
            continue
        resultat.append({
            "tekst": " ".join(tekst.split()),
            "ukedag": dag,
            "fag": fag,
            "dato": l.get("dato")
        })
    return resultat

def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    lekser = filtrer_lekser(data)

    output = {
        "klasse": data.get("klasse", "8E"),
        "lekser": lekser,
        "hentet": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
