from SPARQLWrapper import SPARQLWrapper, JSON
import time
from qualita import quality_score
from typing import List, Dict
from unidecode import unidecode
from info_monumento import extract_description, get_monument_data

HEADERS = {
    "User-Agent": "TRIPlanner/1.0 (for academic use)"
}


def unique_by_label(monuments):
    seen = set()
    result = []
    for m in monuments:
        if m["label"] not in seen:
            result.append(m)
            seen.add(m["label"])
    return result


def fetch_monuments(city: str, limit: int = 100) -> List[Dict]:
    qid = get_city_qid(city)
    if not qid:
        print(f"⚠️ Nessuna QID trovata univoca per la città '{city}'")
        return []
    return fetch_monuments_by_qid(qid, limit)


def plan_itinerary_by_popularity(monuments: List[Dict], days: int, per_day: int = 4) -> List[List[Dict]]:

    groups = {2: [], 1: [], 0: []}
    for m in monuments:
        score = quality_score(m)
        groups[score].append(m)

    itinerary = [[] for _ in range(days)]

    def distribute(monuments_list, start_day, plan):
        day = start_day
        for monument in monuments_list:
            while len(plan[day]) >= per_day:
                day = (day + 1) % days
            plan[day].append(monument)
            day = (day + 1) % days
        return day

    next_day = distribute(groups[2], 0, itinerary)
    next_day = distribute(groups[1], next_day, itinerary)
    distribute(groups[0], next_day, itinerary)

    return itinerary


def find_city_candidates(city_name: str) -> List[Dict[str, str]]:

    sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(120)
    sparql.agent = "Mozilla/5.0 (TRIPlanner/1.0)"

    city_name_normalized = unidecode(city_name.strip().lower())
    query = f"""
    SELECT DISTINCT ?city ?label ?countryLabel (LANG(?label) AS ?labelLang) WHERE {{
      ?city rdfs:label ?label .
      FILTER(LANG(?label) = "it" || LANG(?label) = "en")
      FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{city_name_normalized}")))
      ?city wdt:P31/wdt:P279* wd:Q515 .

      MINUS {{ ?city wdt:P31/wdt:P279* wd:Q24354 }}    # teatro
      MINUS {{ ?city wdt:P31/wdt:P279* wd:Q6581615 }}    # terme
      MINUS {{ ?city wdt:P31/wdt:P279* wd:Q839954 }}   # sito archeologico
      MINUS {{ ?city wdt:P31/wdt:P279* wd:Q13226383 }} # edificio.
      
      OPTIONAL {{ ?city wdt:P17 ?country . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
    }}
    LIMIT 20
    """

    sparql.setQuery(query)

    for attempt in range(3):
        try:
            res = sparql.query().convert()
            city_by_qid = {}
            for b in res["results"]["bindings"]:
                qid = b["city"]["value"].split("/")[-1]

                label = b.get("label", {}).get("value", "")
                lang = b.get("labelLang", {}).get("value", "")
                country = b.get("countryLabel", {}).get("value")

                if not country:
                    continue

                if qid not in city_by_qid:
                    city_by_qid[qid] = {
                        "qid": qid,
                        "label": label,
                        "country": country,
                        "lang": lang
                    }
                else:
                    if lang == "it":
                        city_by_qid[qid]["label"] = label
                        city_by_qid[qid]["lang"] = lang

            return list(city_by_qid.values())

        except Exception as e:
            print(f"❌ Tentativo {attempt + 1} fallito: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                return []


def get_city_qid(city_name: str) -> str:
    cities = find_city_candidates(city_name)
    return cities[0]["qid"] if len(cities) == 1 else None


def fetch_monuments_by_qid(qid: str, limit: int = 100) -> List[Dict]:
    sparql = SPARQLWrapper("https://query.wikidata.org/sparql", agent="TRIPlanner/1.0 "
                                                                      "(offline educational use)")
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(60)

    monument_query = f"""
    SELECT DISTINCT ?itemLabel ?image ?coord ?description WHERE {{
      ?item wdt:P131 wd:{qid} .
      ?item wdt:P31/wdt:P279* ?class .
      VALUES ?class {{
        wd:Q33506   # museo
        wd:Q16970   # chiesa
        wd:Q2977    # cattedrale
        wd:Q163687  # basilica
        wd:Q16966   # duomo
        wd:Q44539   # tempio
        wd:Q811979  # struttura architettonica
        wd:Q570116  # attrazione turistica
        wd:Q24354   # teatro
        wd:Q170980  # obelisco
        wd:Q23413   # castello
        wd:Q483453  # fontana
      }}
      
      MINUS {{ ?item wdt:P31/wdt:P279* wd:Q55488 }}  # escludi stazioni ferroviarie
      MINUS {{ ?item wdt:P31/wdt:P279* wd:Q1248784 }}  # escludi aeroporti
      MINUS {{ ?item wdt:P31/wdt:P279* wd:Q483110 }}  # stadi
      MINUS {{ ?item wdt:P31/wdt:P279* wd:Q16917 }}   # ospedali
      MINUS {{ ?item wdt:P31/wdt:P279* wd:Q3918 }}    # politecnici / università politecniche
      
      OPTIONAL {{ ?item wdt:P18 ?image. }}
      OPTIONAL {{ ?item wdt:P625 ?coord. }}
      OPTIONAL {{ ?item schema:description ?description. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
    }} LIMIT {limit}
    """
    sparql.setQuery(monument_query)
    for attempt in range(3):
        try:
            print("📡 Query da QID in corso...")
            res = sparql.query().convert()
            bindings = res.get("results", {}).get("bindings", [])
            monuments = []

            for b in bindings:
                label = b.get("itemLabel", {}).get("value", "Sconosciuto")

                desc = extract_description(b)
                img = b.get("image", {}).get("value")
                monuments.append(get_monument_data(label, desc, img))

            return unique_by_label(monuments)

        except Exception as e:
            print(f"❌ Tentativo {attempt + 1} fallito: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                return []
