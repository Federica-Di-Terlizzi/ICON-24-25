from typing import Dict


def quality_score(monument: Dict) -> int:

    has_image = monument.get("image")
    has_desc = monument.get("description")

    if not has_desc or has_desc.strip() == "" or has_desc == "Descrizione non disponibile.":
        has_desc = None

    if has_image and ("placeholder" in str(has_image).lower()):
        has_image = None

    if has_image and has_desc:
        return 2
    elif has_image or has_desc:
        return 1
    else:
        return 0
