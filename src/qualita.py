from typing import Dict


def quality_score(monument: Dict) -> int:
    """
    Restituisce un punteggio da 0 a 2 in base alla completezza delle informazioni:
    - 2: immagine e descrizione
    - 1: una sola delle due
    - 0: nessuna delle due
    """
    has_image = monument.get("image")
    has_desc = monument.get("description")

    # ✅ Controllo descrizione
    if not has_desc or has_desc.strip() == "" or has_desc == "Descrizione non disponibile.":
        has_desc = None

    # ✅ Controllo immagine
    if has_image and ("placeholder" in str(has_image).lower()):
        has_image = None

    # Calcolo punteggio
    if has_image and has_desc:
        return 2
    elif has_image or has_desc:
        return 1
    else:
        return 0
