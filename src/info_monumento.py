import requests
from typing import Dict

HEADERS = {"User-Agent": "TRIPlanner/1.0 (for academic use)"}


def extract_description(binding):
    """Estrae descrizione in IT se disponibile, altrimenti EN."""
    desc_it, desc_en = "", ""
    if "description" in binding:
        lang = binding["description"].get("xml:lang")
        text = binding["description"]["value"]
        if lang == "it":
            desc_it = text
        elif lang == "en":
            desc_en = text
    return desc_it or desc_en or ""


def assign_source(data, fallback_data, source_name):
    """Assegna la fonte ai dati di immagine o descrizione."""
    if not data and fallback_data:
        return fallback_data, source_name
    if data:
        return data, source_name
    return data, "Nessuna"


def _fetch_wikipedia_summary(title: str, lang: str) -> Dict[str, str]:
    try:
        endpoint = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
        res = requests.get(endpoint, headers=HEADERS, timeout=5)
        res.raise_for_status()
        js = res.json()
        return {
            "description": js.get("extract"),
            "image": js.get("thumbnail", {}).get("source")
        }
    except (requests.RequestException, ValueError):
        return {}


def _search_and_fetch_wikipedia(label: str, lang: str) -> Dict[str, str]:
    try:
        search_url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {"action": "query", "list": "search", "srsearch": label, "format": "json"}
        res = requests.get(search_url, params=params, headers=HEADERS, timeout=5)
        res.raise_for_status()
        results = res.json().get("query", {}).get("search", [])
        if not results:
            return {}
        best_title = results[0]["title"]
        return _fetch_wikipedia_summary(best_title, lang)
    except (requests.RequestException, ValueError):
        return {}


def _update_if_missing(data: Dict, js: Dict, lang: str, source_prefix: str):
    """
    Aggiorna i campi description/image SOLO se mancanti,
    assegnando anche la fonte.
    """
    if not data["description"] and js.get("description"):
        data["description"], data["description_source"] = assign_source(
            data["description"], js["description"], f"{source_prefix}-{lang}"
        )
    if not data["image"] and js.get("image"):
        data["image"], data["image_source"] = assign_source(
            data["image"], js["image"], f"{source_prefix}-{lang}"
        )


def get_monument_data(label: str, desc: str = None, img: str = None) -> Dict[str, str]:
    """
    Recupera dati completi di un monumento da Wikidata, Wikipedia e Commons.
    """
    data = dict(
        label=label,
        description=None,
        description_source="Nessuna",
        image=None,
        image_source="Nessuna"
    )

    # Primo tentativo: Wikidata (se già forniti)
    data["description"], data["description_source"] = assign_source(desc, None, "Wikidata")
    data["image"], data["image_source"] = assign_source(img, None, "Wikidata")

    # Wikipedia summary
    for lang in ["it", "en"]:
        js = _fetch_wikipedia_summary(label, lang)
        _update_if_missing(data, js, lang, "Wikipedia-summary")

    # Wikipedia search
    for lang in ["it", "en"]:
        js = _search_and_fetch_wikipedia(label, lang)
        _update_if_missing(data, js, lang, "Wikipedia-search")

    # Commons fallback (solo immagine)
    if not data["image"]:
        commons_url = "https://commons.wikimedia.org/w/api.php"
        params = {"action": "query", "titles": label, "prop": "pageimages",
                  "pithumbsize": 600, "format": "json"}
        try:
            res = requests.get(commons_url, params=params, headers=HEADERS, timeout=5)
            res.raise_for_status()
            pages = res.json().get("query", {}).get("pages", {})
            for p in pages.values():
                if "thumbnail" in p and "source" in p["thumbnail"]:
                    data["image"], data["image_source"] = assign_source(
                        data["image"], p["thumbnail"]["source"], "Wikimedia Commons"
                    )
                    break
        except requests.RequestException:
            pass

    if not data["description"]:
        data["description"], data["description_source"] = assign_source(
            data["description"], "Descrizione non disponibile.", "Nessuna"
        )

    return data
