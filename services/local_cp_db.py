import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Minimum local database of postal codes (Valencia and surroundings, expandable)
# Format: "CP": {"poblacion": "NAME", "provincia": "PROVINCIA", "descripcion_provincia": "PROVINCIA"}
_LOCAL_CP_DB = {
    "46025": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46001": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46002": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46003": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46004": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46005": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46006": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46007": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46008": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46009": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46010": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46011": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46012": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46013": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46014": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46015": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46016": {"poblacion": "TAVERNES BLANQUES", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46017": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46018": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46019": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46020": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46021": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46022": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46023": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46024": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46026": {"poblacion": "VALENCIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46100": {"poblacion": "BURJASSOT", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46110": {"poblacion": "GODELLA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46111": {"poblacion": "ROCAFORT", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46113": {"poblacion": "MONCADA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46117": {"poblacion": "BETERA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46120": {"poblacion": "ALBORAYA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46130": {"poblacion": "MASSAMAGRELL", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46131": {"poblacion": "BONREPOS I MIRAMBELL", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46132": {"poblacion": "ALMASSERA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46133": {"poblacion": "MELIANA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46134": {"poblacion": "FOIOS", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46135": {"poblacion": "ALBALAT DELS SORELLS", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46136": {"poblacion": "MUSEROS", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46137": {"poblacion": "LA POBLA DE FARNALS", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46138": {"poblacion": "RAFELBUNYOL", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46139": {"poblacion": "EL PUIG", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46183": {"poblacion": "L'ELIANA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46185": {"poblacion": "LA POBLA DE VALLBONA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46190": {"poblacion": "RIBA-ROJA DE TURIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46200": {"poblacion": "PAIPORTA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46210": {"poblacion": "PICANYA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46220": {"poblacion": "PICASSENT", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46230": {"poblacion": "ALGINET", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46240": {"poblacion": "CARLET", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46250": {"poblacion": "L'ALCUDIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46260": {"poblacion": "ALBERIC", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46290": {"poblacion": "ALCASSER", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46400": {"poblacion": "CULLERA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46410": {"poblacion": "SUECA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46460": {"poblacion": "SILLA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46470": {"poblacion": "CATARROJA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46500": {"poblacion": "SAGUNTO", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46520": {"poblacion": "PUERTO DE SAGUNTO", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46530": {"poblacion": "PUZOL", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46600": {"poblacion": "ALZIRA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46680": {"poblacion": "ALGEMESI", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46700": {"poblacion": "GANDIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46730": {"poblacion": "GRAO DE GANDIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46800": {"poblacion": "XATIVA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46870": {"poblacion": "ONTINYENT", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46900": {"poblacion": "TORRENT", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46910": {"poblacion": "ALFAFAR", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46920": {"poblacion": "MISLATA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46930": {"poblacion": "QUART DE POBLET", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46940": {"poblacion": "MANISES", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46950": {"poblacion": "XIRIVELLA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46960": {"poblacion": "ALDAIA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46970": {"poblacion": "ALAQUAS", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "46980": {"poblacion": "PATERNA", "provincia": "VALENCIA", "descripcion_provincia": "VALENCIA"},
    "28001": {"poblacion": "MADRID", "provincia": "MADRID", "descripcion_provincia": "MADRID"},
    "28002": {"poblacion": "MADRID", "provincia": "MADRID", "descripcion_provincia": "MADRID"},
    "28003": {"poblacion": "MADRID", "provincia": "MADRID", "descripcion_provincia": "MADRID"},
    "08001": {"poblacion": "BARCELONA", "provincia": "BARCELONA", "descripcion_provincia": "BARCELONA"},
    "08002": {"poblacion": "BARCELONA", "provincia": "BARCELONA", "descripcion_provincia": "BARCELONA"},
    "41001": {"poblacion": "SEVILLA", "provincia": "SEVILLA", "descripcion_provincia": "SEVILLA"},
}

def get_local_town_by_cp(cp: str) -> Optional[Dict[str, str]]:
    """
    Searches for a postal code in the local database.
    Returns None if not found.
    """
    cp = cp.strip()
    result = _LOCAL_CP_DB.get(cp)
    
    if result:
        logger.info(f"[LOCAL_CP_DB] Found local fallback for {cp}: {result['poblacion']}")
        return {
            "success": True,
            "poblacion": result["poblacion"],
            "provincia": result["provincia"],
            "descripcion_provincia": result["descripcion_provincia"]
        }
    
    return None
