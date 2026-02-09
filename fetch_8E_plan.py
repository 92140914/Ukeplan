import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin
import json

BASE_URL = "https://www.bergen.kommune.no/omkommunen/avdelinger/mjolkeraen-skole/arbeidsplaner"
OUTPUT_JSON = "ukeplan-8E.json"

# Parser for å finne <a href="..."> lenker
class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = None
            text = ""
            for attr, val in attrs:
                if attr.lower() == "href":
                    href = val
            self.links.append((href, ""))

    def handle_data(self, data):
        if self.links:
            href, _ = self.links[-1]
            self.links[-1] = (href, data.strip())

def get_links(url):
    """Returnerer liste av (href, text) fra siden"""
    with urllib.request.urlopen(url) as response:
        html = response.read().decode("utf-8")
    parser = LinkParser()
    parser.feed(html)
    # Filtrer bort lenker uten href
    return [(href, text) for href, text in parser.links if href]

def find_link_by_keywords(links, keywords):
    """Finn første lenke hvor teksten inneholder ett av keywordene"""
    for href, text in links:
        for kw in keywords:
            if kw.lower() in text.lower():
                return href
    return None

def main():
    # 1️⃣ Hent lenker til uke
    links = get_links(BASE_URL)
    uke_href = find_link_by_keywords(links, ["Nåværende uke", "Neste uke"])
    if not uke_href:
        print("Fant ikke lenke til uke")
        return
    uke_url = urljoin(BASE_URL, uke_href)

    # 2️⃣ Hent lenker til klasse 8E
    links_uke = get_links(uke_url)
    klasse_href = find_link_by_keywords(links_uke, ["8E", "8 E", "8. E"])
    if not klasse_href:
        print("Fant ikke lenke til klasse 8E")
        return
    klasse_url = urljoin(uke_url, klasse_href)

    # 3️⃣ Hent PDF-lenker fra 8E-siden
    links_8e = get_links(klasse_url)
    pdf_urls = []
    for href, text in links_8e:
        if ".pdf" in href.lower():
            pdf_urls.append(urljoin(klasse_url, href))

    # 4️⃣ Lagre i JSON
    result = {
        "scrape_time": "2026-02-09T00:00:00Z",
        "source": BASE_URL,
        "uke_url": uke_url,
        "klasse_url": klasse_url,
        "pdfs": [{"url": url} for url in pdf_urls]
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Ferdig! PDF-lenker lagret i {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
