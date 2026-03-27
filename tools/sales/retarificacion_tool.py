"""Tools for pricing in Merlin Multitarificador (Auto and Home).

Contains five tools:
  1. consulta_vehiculo_tool: DGT lookup by license plate (via ERP).
  2. get_town_by_cp_tool: Gets town/city by postal code (via ERP).
  3. consultar_catastro_tool: Cadastre lookup and capital calculation (via ERP).
  4. create_retarificacion_project_tool: Creates final project in Merlin (via ERP).
  5. finalizar_proyecto_hogar_tool: Finalizes HOME project with chosen capitals (via ERP).

NOTE: These tools call the ERP webservice (ebroker-api) which centralizes the logic.
"""

import json
import logging
from langchain.tools import tool
from services.erp_client import ERPClient

logger = logging.getLogger(__name__)

_project_ids: dict = {"proyecto_id": None, "id_pasarela": None}


def get_last_project_ids():
    """Return (proyecto_id, id_pasarela) stored by the last tool invocation, then clear them."""
    pid = _project_ids.get("proyecto_id")
    pas = _project_ids.get("id_pasarela")
    logger.info(f"[PROJECT_IDS] get_last_project_ids called: pid={pid}, pas={pas}")
    _project_ids["proyecto_id"] = None
    _project_ids["id_pasarela"] = None
    return pid, pas

_REQUIRED_FIELDS_AUTO = ["dni", "matricula", "fecha_efecto"]
_REQUIRED_FIELDS_HOGAR = ["dni", "codigo_postal", "fecha_efecto", "nombre_via", "numero_calle", "tipo_vivienda"]


# ============================================================================
# TOOL 1: Vehicle Lookup (DGT) - AUTO only
# ============================================================================

@tool
def consulta_vehiculo_tool(matricula: str, company_id: str) -> dict:
    """
    Look up technical data for a vehicle in the DGT using its license plate.
    Returns make, model, version, fuel, garage, km, dates, etc.

    Use this tool as soon as the client provides the license plate.
    Show the data to the client in a BULLET LIST and ask if it is correct.

    Args:
        matricula: Vehicle license plate (e.g. "3492GYW")
        company_id: Company ID (automatically obtained from context)

    Returns:
        dict with vehicle data retrieved from DGT.
    """
    matricula = matricula.strip().upper()
    logger.info(f"[CONSULTA_VEHICULO] Looking up vehicle: {matricula}")
    
    client = ERPClient(company_id)
    result = client.merlin_consulta_vehiculo(matricula)

    if result.get("success"):
        datos = result.get("datos_vehiculo", {})
        if not datos and "raw_data" in result:
             v = result["raw_data"]
             def clean(val):
                s = str(val).strip() if val is not None else ""
                return s if s else "No especificado"
             
             datos = {
                "Marca": clean(v.get("marca")),
                "Modelo": clean(v.get("modelo")),
                "Versión": clean(v.get("version")),
                "Combustible": clean(v.get("combustible_descripcion")),
                "Fecha de Matriculación": clean(v.get("fecha_matriculacion")),
                "Kilómetros Anuales": clean(v.get("km_anuales")),
                "Kilómetros Totales": clean(v.get("km_totales")),
                "Garaje": clean(v.get("garaje")),
            }
            
        logger.info(f"[CONSULTA_VEHICULO] Found: {datos.get('Marca')} {datos.get('Modelo')}")
        return {
            "success": True,
            "datos_vehiculo": datos
        }
    else:
        logger.error(f"[CONSULTA_VEHICULO] Failed: {result.get('error')}")
        return result


# ============================================================================
# TOOL 2: Town/City Lookup (CP) - Both lines
# ============================================================================

@tool
def get_town_by_cp_tool(cp: str, company_id: str) -> dict:
    """
    Retrieves town/city and province from a postal code.

    Use this tool as soon as the client provides the postal code.
    Show the town to the client and ask if it is correct.

    Args:
        cp: Postal code (e.g. "28001")
        company_id: Company ID (automatically obtained from context)

    Returns:
        dict with town and province.
    """
    cp = cp.strip()
    logger.info(f"[GET_TOWN_BY_CP] Looking up CP: {cp}")
    
    client = ERPClient(company_id)
    result = client.merlin_get_town_by_cp(cp)
    
    if result.get("success"):
        logger.info(f"[GET_TOWN_BY_CP] Found: {result.get('poblacion')} ({result.get('descripcion_provincia')})")
        return result
    
    # Fallback to local DB if ERP fails
    logger.warning(f"[GET_TOWN_BY_CP] ERP failed: {result.get('error')}. Trying local fallback.")
    try:
        from services.local_cp_db import get_local_town_by_cp
        local_result = get_local_town_by_cp(cp)
        if local_result:
            logger.info(f"[GET_TOWN_BY_CP] Local DB SUCCESS for {cp}: {local_result.get('poblacion')}")
            return local_result
    except Exception as e:
        logger.error(f"[GET_TOWN_BY_CP] Local DB import/query failed: {e}")

    # If local fallback fails, try ERP again with a small retry (sometimes Cloud Run cold starts or timeouts)
    logger.warning(f"[GET_TOWN_BY_CP] Local fallback failed for {cp}. Retrying ERP with backoff...")
    import time
    for attempt in range(3): # Up to 3 retries
        wait_time = 1.0 * (attempt + 1)
        logger.info(f"[GET_TOWN_BY_CP] ERP Retry {attempt+1} in {wait_time}s...")
        time.sleep(wait_time)
        result = client.merlin_get_town_by_cp(cp)
        if result.get("success"):
            logger.info(f"[GET_TOWN_BY_CP] ERP Retry {attempt+1} SUCCESS: {result.get('poblacion')}")
            return result
        
    logger.error(f"[GET_TOWN_BY_CP] Failed in ERP (all attempts) and Local DB")
    return result


# ============================================================================
# TOOL 3: Cadastre Lookup (Home)
# ============================================================================

@tool
def consultar_catastro_tool(
    provincia: str,
    municipio: str,
    tipo_via: str,
    nombre_via: str,
    numero: str,
    company_id: str,
    bloque: str = "",
    escalera: str = "",
    planta: str = "",
    puerta: str = "",
    piso: str = "",  # Alias for planta
    numero_personas: str = "3",
    tipo_vivienda: str = "PISO_EN_ALTO",
) -> str:
    """
    Look up technical data for a dwelling in the Cadastre (surface, construction year, use).

    Use this tool as soon as the client provides the full address for Home insurance.
    Show the retrieved data (year and surface) to the client and ask if it is correct.

    Args:
        provincia: Province name (e.g. "MADRID")
        municipio: Town/City name (e.g. "MADRID")
        tipo_via: Road type code (CL, AV, PZ, PO, RD, CLZ, CM)
        nombre_via: Road name (e.g. "ALCALA")
        numero: Road number (e.g. "5")
        company_id: Company ID (automatically obtained from context)
        bloque: Block (optional)
        escalera: Staircase (optional)
        planta: Floor (e.g. "5")
        puerta: Door (e.g. "A")
        piso: Alias for floor (optional)
        numero_personas: Number of people in the house (e.g. "3")
        tipo_vivienda: Dwelling type (PISO_EN_ALTO, PISO_EN_BAJO, ATICO, CHALET_O_VIVIENDA_UNIFAMILIAR, CHALET_O_VIVIENDA_ADOSADA)
    """
    final_planta = planta or piso
    
    logger.info(f"[CONSULTAR_CATASTRO] Looking up: {tipo_via} {nombre_via} {numero} {final_planta} {puerta} in {municipio} ({provincia})")
    
    payload = {
        "provincia": provincia,
        "municipio": municipio,
        "tipo_via": tipo_via,
        "nombre_via": nombre_via,
        "numero": numero,
        "bloque": bloque,
        "escalera": escalera,
        "planta": final_planta,
        "puerta": puerta,
        "tipo_vivienda": tipo_vivienda
    }
    
    client = ERPClient(company_id)
    result = client.merlin_consultar_catastro(payload)
    
    if result.get("success") or "anio_construccion" in result:
        anio = result.get("anio_construccion", "NO DISPONIBLE")
        superficie = result.get("superficie", "NO DISPONIBLE")
        ref = result.get("referencia_catastral", "")
        cp_catastro = result.get("codigo_postal", "")
        
        capital_continente = result.get("capital_continente") or 150000
        capital_contenido = result.get("capital_contenido") or 25000
        precio_m2_base = result.get("precio_m2_base", 1500)
        factor_tipologia = result.get("factor_tipologia", 1.0)
        precio_m2_contenido = result.get("precio_m2_contenido", 250)
        
        logger.info(f"[CONSULTAR_CATASTRO] SUCCESS - Año: {anio}, Superficie: {superficie}m²")

        return (
            f"DATOS ENCONTRADOS: Año: {anio}, Superficie: {superficie}, Ref: {ref}, CP: {cp_catastro}\n"
            f"VALORES SUGERIDOS (CONFIRMAR CON CLIENTE):\n"
            f"- Situación: NUCLEO_URBANO\n"
            f"- Régimen: PROPIEDAD\n"
            f"- Uso: VIVIENDA_HABITUAL\n"
            f"- Utilización: VIVIENDA_EXCLUSIVAMENTE\n"
            f"- Nº Personas: {numero_personas}\n"
            f"- Calidad: NORMAL\n"
            f"- Materiales: SOLIDA_PIEDRAS_LADRILLOS_ETC\n"
            f"- Tuberías: POLIPROPILENO\n"
            f"PROTECCIONES (POR DEFECTO):\n"
            f"- Puerta principal: DE_MADERA_PVC_METALICA_ETC\n"
            f"- Puerta secundaria: NO_TIENE\n"
            f"- Ventanas: SIN_PROTECCION\n"
            f"- Alarmas (Robo/Incendio/Agua): SIN_ALARMA\n"
            f"- Caja fuerte: NO_TIENE\n"
            f"- Vigilancia: SIN_VIGILANCIA\n"
            f"CAPITALES RECOMENDADOS (USAR EN PASO 6):\n"
            f"- Capital Continente Recomendado: {capital_continente} € (Precio base zona: {int(precio_m2_base)} €/m² | Factor tipo {tipo_vivienda}: {factor_tipologia}x)\n"
            f"- Capital Contenido Recomendado: {capital_contenido} € (Calculado a {precio_m2_contenido} €/m² según tipo {tipo_vivienda})"
        )
    else:
        err = result.get('error', 'Desconocido')
        logger.error(f"[CONSULTAR_CATASTRO] Failed: {err}")
        return f"NO SE ENCONTRARON DATOS: {err}. Usa valores por defecto."


# ============================================================================
# TOOL 4: Project creation in Merlin (Auto or Home)
# ============================================================================

@tool
def create_retarificacion_project_tool(data: str, company_id: str) -> dict:
    """
    Creates a project for insurance pricing (Auto or Home) in Merlin.
    Automatically enriches data using DGT, ERP, Cadastre and location services.
    
    If pricing is successful, returns the full 'proyecto' object with insurance offers
    in the 'tarificaciones' or 'afinaciones' field.

    Input: JSON string with collected data.

    Args:
        data: JSON string with all collected client data
        company_id: Company ID (automatically obtained from context)
    """
    logger.info(f"[RETARIFICACION] === RAW LLM DATA (first 3000 chars) ===")
    logger.info(f"[RETARIFICACION] {data[:3000]}")
    logger.info(f"[RETARIFICACION] === END RAW DATA ===")

    try:
        payload = json.loads(data)
    except json.JSONDecodeError as e:
        logger.error(f"[RETARIFICACION] JSON parse error: {e}")
        return {"success": False, "error": f"Formato JSON inválido: {e}"}

    if "nif" in payload and "dni" not in payload:
        payload["dni"] = payload.pop("nif")

    _MATERIALES_NORMALIZE = {
        "SOLIDA": "SOLIDA_PIEDRAS_LADRILLOS_ETC",
        "SOLIDA_PIEDRAS": "SOLIDA_PIEDRAS_LADRILLOS_ETC",
    }
    mat = str(payload.get("materiales_construccion", "")).upper()
    if mat in _MATERIALES_NORMALIZE:
        payload["materiales_construccion"] = _MATERIALES_NORMALIZE[mat]

    ramo = str(payload.get("ramo", "")).upper()
    
    if not ramo:
        hogar_indicators = ["capital_continente", "capital_contenido", "nombre_via", "regimen_ocupacion", "tipo_vivienda", "situacion_vivienda"]
        if any(payload.get(k) for k in hogar_indicators):
            ramo = "HOGAR"
            payload["ramo"] = "HOGAR"
        else:
            ramo = "AUTO"
            payload["ramo"] = "AUTO"
        logger.info(f"[RETARIFICACION] Ramo not specified, inferred: {ramo}")
    
    required = _REQUIRED_FIELDS_AUTO if ramo == "AUTO" else _REQUIRED_FIELDS_HOGAR
    missing = [f for f in required if not payload.get(f)]
    if missing:
        logger.error(f"[RETARIFICACION] Missing fields for {ramo}: {missing}")
        return {
            "success": False,
            "error": f"Campos obligatorios faltantes para {ramo}: {', '.join(missing)}",
        }
    
    logger.info(f"[RETARIFICACION] Delegating {ramo} project to ERP for DNI: {payload.get('dni')}")
    logger.info(f"[RETARIFICACION] Payload keys: {sorted(payload.keys())}")
    logger.info(f"[RETARIFICACION] Key values: ramo={ramo}, tipo_vivienda={payload.get('tipo_vivienda')}, cp={payload.get('codigo_postal')}, fecha_efecto={payload.get('fecha_efecto')}")
    
    if ramo == "HOGAR":
        logger.info(f"[RETARIFICACION] Address: via={payload.get('nombre_via')}, num={payload.get('numero_calle')}, piso={payload.get('piso')}, puerta={payload.get('puerta')}")
        logger.info(f"[RETARIFICACION] Capitals: continente={payload.get('capital_continente')} (type={type(payload.get('capital_continente')).__name__}), contenido={payload.get('capital_contenido')} (type={type(payload.get('capital_contenido')).__name__})")
    
    client = ERPClient(company_id)
    payload["max_wait_polling"] = 30
    payload["poll_interval"] = 2
    result = client.merlin_create_project(payload)
    
    if result.get("success"):
        pid = result.get('proyecto_id')
        pas = result.get('id_pasarela')
        logger.info(f"[RETARIFICACION] Project created successfully: ID={pid}, pasarela={pas}, msg={result.get('mensaje')}")

        if pid and pas:
            _project_ids["proyecto_id"] = str(pid)
            _project_ids["id_pasarela"] = int(pas)
            logger.info(f"[PROJECT_IDS] Stored: proyecto_id={_project_ids['proyecto_id']}, id_pasarela={_project_ids['id_pasarela']}")
        
        # Deduplicate offers if present (for AUTO and non-HOGAR projects)
        if "ofertas" in result:
            ofertas_raw = result.get("ofertas", [])
            seen_offers = set()
            ofertas_dedup = []
            for o in ofertas_raw:
                key = (
                    str(o.get("nombre_aseguradora", "")).strip().upper(),
                    str(o.get("prima_anual", "")).strip()
                )
                if key not in seen_offers:
                    seen_offers.add(key)
                    ofertas_dedup.append(o)
            result["ofertas"] = ofertas_dedup
            logger.info(f"[RETARIFICACION] Deduplicated to {len(ofertas_dedup)} offers")
    else:
        logger.error(f"[RETARIFICACION] FAILED: {result.get('error')}")
        logger.error(f"[RETARIFICACION] Full error result: {json.dumps(result, default=str, ensure_ascii=False)[:1000]}")

    return result


# ============================================================================
# TOOL 5: Finalize HOME project with chosen capitals
# ============================================================================

@tool
def finalizar_proyecto_hogar_tool(
    proyecto_id: str,
    id_pasarela: int,
    capital_continente: int,
    capital_contenido: int,
    fecha_efecto: str,
    company_id: str,
) -> dict:
    """
    Finalizes a HOME project in Merlin with capitals chosen by the client
    and launches multi-insurer pricing.

    Use this tool AFTER create_retarificacion_project_tool has returned
    action_required='select_capitals' and the client has chosen their preferred capitals
    from the recommendations per insurer.

    Args:
        proyecto_id: MongoDB project ID ("proyecto_id" field returned by create_retarificacion_project_tool, e.g. "69a6c89815a9590f351dc961")
        id_pasarela: Numeric gateway ID ("id_pasarela" field returned by create_retarificacion_project_tool, e.g. 3410). MUST be an integer.
        capital_continente: Continent capital chosen by the client (e.g. 150000)
        capital_contenido: Content capital chosen by the client (e.g. 30000)
        fecha_efecto: Policy effective date (YYYY-MM-DD format)
        company_id: Company ID (automatically obtained from context)

    Returns:
        dict with pricing result, including insurer offers.
    """
    logger.info(
        f"[FINALIZAR_HOGAR] project={proyecto_id}, pasarela={id_pasarela}, "
        f"continente={capital_continente}, contenido={capital_contenido}"
    )

    client = ERPClient(company_id)
    result = client.merlin_finalizar_proyecto_hogar({
        "proyecto_id": proyecto_id,
        "id_pasarela": id_pasarela,
        "capital_continente": capital_continente,
        "capital_contenido": capital_contenido,
        "fecha_efecto": fecha_efecto,
        "max_wait_polling": 30,
        "poll_interval": 2,
    })

    if result.get("success"):
        ofertas_raw = result.get("ofertas", [])
        logger.info(f"[FINALIZAR_HOGAR] Success: {len(ofertas_raw)} raw offers returned")
        
        # Deduplicate offers by insurer name and annual premium
        seen_offers = set()
        ofertas_dedup = []
        for o in ofertas_raw:
            # Create a unique key for the offer
            key = (
                str(o.get("nombre_aseguradora", "")).strip().upper(),
                str(o.get("prima_anual", "")).strip()
            )
            if key not in seen_offers:
                seen_offers.add(key)
                ofertas_dedup.append(o)
        
        logger.info(f"[FINALIZAR_HOGAR] Deduplicated to {len(ofertas_dedup)} offers")
        result["ofertas"] = ofertas_dedup
    else:
        logger.error(f"[FINALIZAR_HOGAR] FAILED: {result.get('error')}")

    return result
