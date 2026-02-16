"""Cliente para la API pública del Catastro (Sede Electrónica).

Consulta datos no protegidos de inmuebles (superficie, año de construcción, uso)
a partir de la dirección (provincia, municipio, tipo vía, nombre vía, número).

API: https://ovc.catastro.meh.es/ovcservweb/ovcswlocalizacionrc/ovccallejero.asmx
Endpoint usado: Consulta_DNPLOC (HTTP GET, sin autenticación, XML response).
"""

import logging
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

CATASTRO_BASE_URL = (
    "https://ovc.catastro.meh.es/ovcservweb/ovcswlocalizacionrc/ovccallejero.asmx"
)
CATASTRO_TIMEOUT = 15


def consultar_catastro_por_direccion(
    provincia: str,
    municipio: str,
    tipo_via: str,
    nombre_via: str,
    numero: str,
    bloque: str = "",
    escalera: str = "",
    planta: str = "",
    puerta: str = "",
) -> Dict[str, Any]:
    """Query the Catastro for property data by address.

    Args:
        provincia: Province name (e.g. "MADRID")
        municipio: Municipality name (e.g. "MADRID")
        tipo_via: Street type abbreviation (e.g. "CL", "AV", "PZ")
        nombre_via: Street name (e.g. "GRAN VIA")
        numero: Street number (e.g. "1")
        bloque/escalera/planta/puerta: Optional location details

    Returns:
        dict with success flag and property data (superficie, anio_construccion, uso, ref_catastral).
    """
    params = {
        "Provincia": provincia.strip().upper(),
        "Municipio": municipio.strip().upper(),
        "Sigla": tipo_via.strip().upper(),
        "Calle": nombre_via.strip().upper(),
        "Numero": str(numero).strip(),
        "Bloque": bloque.strip(),
        "Escalera": escalera.strip(),
        "Planta": planta.strip(),
        "Puerta": puerta.strip(),
    }

    url = f"{CATASTRO_BASE_URL}/Consulta_DNPLOC"
    logger.info(f"[CATASTRO] Querying: {params['Provincia']}, {params['Municipio']}, "
                f"{params['Sigla']} {params['Calle']} {params['Numero']}")

    try:
        resp = requests.get(url, params=params, timeout=CATASTRO_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error(f"[CATASTRO] Request failed: {exc}")
        return {"success": False, "error": f"Error consultando el Catastro: {exc}"}

    return _parse_catastro_response(resp.text)


def _parse_catastro_response(xml_text: str) -> Dict[str, Any]:
    """Parse the Catastro XML response extracting property data."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error(f"[CATASTRO] XML parse error: {exc}")
        return {"success": False, "error": "Error parseando respuesta del Catastro"}

    ns = _detect_namespace(root)

    # Check for errors
    error_elem = root.find(f".//{ns}err") if ns else root.find(".//err")
    if error_elem is not None:
        error_desc = _find_text(error_elem, "des", ns) or "Error desconocido"
        error_code = _find_text(error_elem, "cod", ns) or ""
        logger.warning(f"[CATASTRO] API error {error_code}: {error_desc}")

        # If multiple properties found, return list of candidates
        candidates = _extract_candidates(root, ns)
        if candidates:
            return {
                "success": False,
                "error": error_desc,
                "multiple_results": True,
                "candidates": candidates,
            }
        return {"success": False, "error": error_desc}

    # Look for property data (bico = bien inmueble completo)
    bico = root.find(f".//{ns}bico") if ns else root.find(".//bico")
    if bico is None:
        # Try to find list of properties (lrcdnp)
        candidates = _extract_candidates(root, ns)
        if candidates:
            return {
                "success": False,
                "error": "Se encontraron múltiples inmuebles. Especifica planta y puerta.",
                "multiple_results": True,
                "candidates": candidates,
            }
        return {"success": False, "error": "No se encontraron datos del inmueble"}

    # Extract property details
    bi = bico.find(f"{ns}bi") if ns else bico.find("bi")
    debi = bi.find(f"{ns}debi") if bi is not None else None
    lcons = bi.find(f"{ns}lcons") if bi is not None else None
    idbi = bi.find(f"{ns}idbi") if bi is not None else None

    result: Dict[str, Any] = {"success": True}

    # Cadastral reference
    rc = _extract_ref_catastral(idbi, ns)
    if rc:
        result["referencia_catastral"] = rc

    # Address from response
    dt = idbi.find(f"{ns}dt") if idbi is not None else None
    if dt is not None:
        locs = dt.find(f"{ns}locs") if ns else dt.find("locs")
        if locs is not None:
            lous = locs.find(f"{ns}lous") if ns else locs.find("lous")
            if lous is not None:
                lourb = lous.find(f"{ns}lourb") if ns else lous.find("lourb")
                if lourb is not None:
                    result["bloque"] = _find_text(lourb, "bq", ns) or ""
                    result["escalera"] = _find_text(lourb, "es", ns) or ""
                    result["planta"] = _find_text(lourb, "pt", ns) or ""
                    result["puerta"] = _find_text(lourb, "pu", ns) or ""

    # Economic/construction data
    if debi is not None:
        sfc = _find_text(debi, "sfc", ns)
        if sfc:
            try:
                result["superficie"] = int(sfc)
            except ValueError:
                result["superficie"] = sfc

        ant = _find_text(debi, "ant", ns)
        if ant:
            try:
                result["anio_construccion"] = int(ant)
            except ValueError:
                result["anio_construccion"] = ant

        uso = _find_text(debi, "luso", ns)
        if uso:
            result["uso"] = uso

        cpt = _find_text(debi, "cpt", ns)
        if cpt:
            result["coeficiente_participacion"] = cpt

    # Construction units (lcons) - extract to determine type
    if lcons is not None:
        units = lcons.findall(f"{ns}cons") if ns else lcons.findall("cons")
        construction_units = []
        for unit in units:
            lcd = _find_text(unit, "lcd", ns) or ""
            dfcons = unit.find(f"{ns}dfcons") if ns else unit.find("dfcons")
            stl = _find_text(dfcons, "stl", ns) if dfcons is not None else None
            construction_units.append({
                "uso": lcd,
                "superficie": int(stl) if stl and stl.isdigit() else stl,
            })
        if construction_units:
            result["unidades_constructivas"] = construction_units

    logger.info(
        f"[CATASTRO] Found: ref={result.get('referencia_catastral', '?')}, "
        f"superficie={result.get('superficie', '?')}m², "
        f"año={result.get('anio_construccion', '?')}, "
        f"uso={result.get('uso', '?')}"
    )
    return result


def _detect_namespace(root: ET.Element) -> str:
    """Detect XML namespace from root element tag."""
    tag = root.tag
    if tag.startswith("{"):
        ns_end = tag.index("}")
        return tag[:ns_end + 1]
    return ""


def _find_text(parent: Optional[ET.Element], tag: str, ns: str) -> Optional[str]:
    """Find text content of a child element, namespace-aware."""
    if parent is None:
        return None
    elem = parent.find(f"{ns}{tag}") if ns else parent.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    return None


def _extract_ref_catastral(idbi: Optional[ET.Element], ns: str) -> Optional[str]:
    """Extract full cadastral reference from idbi element."""
    if idbi is None:
        return None
    rc = idbi.find(f"{ns}rc") if ns else idbi.find("rc")
    if rc is None:
        return None
    pc1 = _find_text(rc, "pc1", ns) or ""
    pc2 = _find_text(rc, "pc2", ns) or ""
    car = _find_text(rc, "car", ns) or ""
    cc1 = _find_text(rc, "cc1", ns) or ""
    cc2 = _find_text(rc, "cc2", ns) or ""
    return f"{pc1}{pc2}{car}{cc1}{cc2}" if pc1 else None


def _extract_candidates(root: ET.Element, ns: str) -> list:
    """Extract list of candidate properties when multiple matches found."""
    candidates = []
    # Look for rcdnp elements (referencia catastral datos no protegidos)
    rcdnp_list = root.findall(f".//{ns}rcdnp") if ns else root.findall(".//rcdnp")
    for rcdnp in rcdnp_list[:10]:
        rc1 = _find_text(rcdnp, "rc1", ns) or ""
        rc2 = _find_text(rcdnp, "rc2", ns) or ""
        rc3 = _find_text(rcdnp, "rc3", ns) or ""
        rc4 = _find_text(rcdnp, "rc4", ns) or ""

        dt = rcdnp.find(f"{ns}dt") if ns else rcdnp.find("dt")
        locs = dt.find(f"{ns}locs") if dt is not None else None
        lous = locs.find(f"{ns}lous") if locs is not None else None
        lourb = lous.find(f"{ns}lourb") if lous is not None else None

        candidate = {"ref_catastral": f"{rc1}{rc2}{rc3}{rc4}"}
        if lourb is not None:
            candidate["bloque"] = _find_text(lourb, "bq", ns) or ""
            candidate["escalera"] = _find_text(lourb, "es", ns) or ""
            candidate["planta"] = _find_text(lourb, "pt", ns) or ""
            candidate["puerta"] = _find_text(lourb, "pu", ns) or ""

        candidates.append(candidate)

    return candidates
