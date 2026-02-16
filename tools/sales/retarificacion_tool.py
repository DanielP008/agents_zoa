"""Tools para tarificación en Merlin Multitarificador (Auto y Hogar).

Contiene tres herramientas:
  1. consulta_vehiculo_tool: Consulta DGT por matrícula y muestra datos al cliente.
  2. get_town_by_cp_tool: Obtiene población por código postal.
  3. create_retarificacion_project_tool: Crea el proyecto final en Merlin (Auto o Hogar).
"""

import json
import logging
from langchain.tools import tool
from services.merlin_client import create_merlin_project, get_vehicle_info_by_matricula, get_town_by_cp
from services.erp_client import get_policy_by_risk_from_erp

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS_AUTO = ["dni", "matricula", "fecha_efecto"]
_REQUIRED_FIELDS_HOGAR = ["dni", "codigo_postal", "anio_construccion", "superficie_vivienda", "fecha_efecto"]


# ============================================================================
# TOOL 1: Consulta de vehículo (DGT) - Solo AUTO
# ============================================================================

@tool
def consulta_vehiculo_tool(matricula: str) -> dict:
    """
    Consulta los datos técnicos de un vehículo en la DGT a partir de su matrícula.
    Devuelve marca, modelo, versión, combustible, garaje, km, fechas, etc.

    Usa esta herramienta en cuanto el cliente proporcione la matrícula.
    Muestra los datos al cliente en una LISTA DE PUNTOS y pregúntale si son correctos.

    Args:
        matricula: Matrícula del vehículo (ej: "3492GYW")

    Returns:
        dict con los datos del vehículo recuperados de la DGT.
    """
    matricula = matricula.strip().upper()
    logger.info(f"[CONSULTA_VEHICULO] Looking up vehicle: {matricula}")
    dgt_result = get_vehicle_info_by_matricula(matricula)

    if dgt_result.get("success"):
        v = dgt_result.get("vehiculo", {})
        logger.info(
            f"[CONSULTA_VEHICULO] Found: {v.get('marca')} {v.get('modelo')} "
            f"({v.get('version')}) - {v.get('combustible_descripcion')}"
        )

        def clean(val):
            if val is None:
                return "No especificado"
            s = str(val).strip()
            return s if s else "No especificado"

        return {
            "success": True,
            "datos_vehiculo": {
                "Marca": clean(v.get("marca")),
                "Modelo": clean(v.get("modelo")),
                "Versión": clean(v.get("version")),
                "Combustible": clean(v.get("combustible_descripcion")),
                "Fecha de Matriculación": clean(v.get("fecha_matriculacion")),
                "Kilómetros Anuales": clean(v.get("km_anuales")),
                "Kilómetros Totales": clean(v.get("km_totales")),
                "Garaje": clean(v.get("garaje")),
            },
        }
    else:
        logger.error(f"[CONSULTA_VEHICULO] Failed: {dgt_result.get('error')}")
        return dgt_result


# ============================================================================
# TOOL 2: Consulta de población (CP) - Ambos ramos
# ============================================================================

@tool
def get_town_by_cp_tool(cp: str) -> dict:
    """
    Obtiene la población y provincia a partir de un código postal.

    Usa esta herramienta en cuanto el cliente proporcione el código postal.
    Muestra la población al cliente y pregúntale si es correcta.

    Args:
        cp: Código postal (ej: "28001")

    Returns:
        dict con la población y provincia.
    """
    cp = cp.strip()
    logger.info(f"[GET_TOWN_BY_CP] Looking up CP: {cp}")
    result = get_town_by_cp(cp)
    if result.get("success"):
        logger.info(f"[GET_TOWN_BY_CP] Found: {result.get('poblacion')} ({result.get('descripcion_provincia')})")
    else:
        logger.error(f"[GET_TOWN_BY_CP] Failed: {result.get('error')}")
    return result


# ============================================================================
# TOOL 3: Creación de proyecto en Merlin (Auto o Hogar)
# ============================================================================

@tool
def create_retarificacion_project_tool(data: str) -> dict:
    """
    Crea un proyecto de tarificación de seguro (Auto o Hogar) en Merlin.
    Enriquece automáticamente los datos usando la DGT, el ERP y servicios de localización.

    Input: JSON string con los datos recopilados.

    Campo de ramo:
    - ramo: str ("AUTO" o "HOGAR", por defecto "AUTO")

    Campos comunes obligatorios:
    - dni: str (NIF/DNI del tomador)
    - fecha_efecto: str ("YYYY-MM-DD")

    Campos adicionales para AUTO:
    - matricula: str (matrícula del vehículo)

    Campos adicionales para HOGAR:
    - codigo_postal: str
    - anio_construccion: int (año de construcción)
    - superficie_vivienda: int (metros cuadrados)
    - tipo_vivienda: str ("PISO", "UNIFAMILIAR", "ADOSADO", etc. - por defecto "PISO")
    - capital_continente: int (valor de la construcción - por defecto 100000)
    - capital_contenido: int (valor del mobiliario - por defecto 10000)
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"success": False, "error": "Formato JSON inválido"}

    ramo = str(payload.get("ramo", "AUTO")).upper()

    required = _REQUIRED_FIELDS_AUTO if ramo == "AUTO" else _REQUIRED_FIELDS_HOGAR
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return {
            "success": False,
            "error": f"Campos obligatorios faltantes para {ramo}: {', '.join(missing)}",
        }

    dni = payload.get("dni")
    cp = payload.get("codigo_postal")

    # 1. Enrichment for AUTO only
    if ramo == "AUTO":
        matricula = payload.get("matricula")
        logger.info(f"[RETARIFICACION] Enriching with DGT for {matricula}")
        dgt_result = get_vehicle_info_by_matricula(matricula)
        if dgt_result.get("success"):
            v = dgt_result.get("vehiculo", {})
            payload.update({
                "marca": v.get("marca"),
                "modelo": v.get("modelo"),
                "version": v.get("version"),
                "combustible": v.get("combustible"),
                "fecha_matriculacion": v.get("fecha_matriculacion"),
                "km_anuales": v.get("km_anuales"),
                "km_totales": v.get("km_totales"),
                "tipo_de_garaje": v.get("garaje") or payload.get("tipo_de_garaje", "COLECTIVO"),
                "id_auto_base7": v.get("id_auto_base7"),
                "id_tipo_base7": v.get("id_tipo_base7"),
                "id_categoria_base7": v.get("id_categoria_base7"),
                "id_clase_base7": v.get("id_clase_base7"),
                "potencia": v.get("potencia_cv"),
                "cilindrada": v.get("cilindrada"),
                "precio_vp": v.get("precio_vp"),
            })

        if dni and matricula:
            company_id = payload.get("company_id", "")
            if company_id:
                logger.info(f"[RETARIFICACION] Checking ERP for policy (DNI={dni}, Risk={matricula})")
                erp_result = get_policy_by_risk_from_erp(dni, matricula, company_id)
                if erp_result.get("success"):
                    policy = erp_result.get("policy", {})
                    payload.update({
                        "aseguradora_actual": policy.get("company_name") or policy.get("company_id"),
                        "num_poliza": policy.get("number"),
                    })

    # 2. Enrichment for both (Town/CP)
    if cp:
        logger.info(f"[RETARIFICACION] Enriching town for CP {cp}")
        town_result = get_town_by_cp(cp)
        if town_result.get("success"):
            payload.update({
                "poblacion": town_result.get("poblacion"),
                "id_provincia": town_result.get("id_provincia"),
                "descripcion_provincia": town_result.get("descripcion_provincia"),
            })

    # 3. Default values for HOGAR
    if ramo == "HOGAR":
        defaults = {
            "tipo_situacion": "NUCLEO_URBANO",
            "regimen_ocupacion": "PROPIEDAD",
            "uso_vivienda": "VIVIENDA_HABITUAL",
            "utilizacion_vivienda": "VIVIENDA_EXCLUSIVAMENTE",
            "calidad_construccion": "NORMAL",
            "materiales_construccion": "SOLIDA_PIEDRAS_LADRILLOS_ETC",
            "tipo_tuberias": "POLIPROPILENO",
            "tipo_puerta": "DE_MADERA_PVC_METALICA_ETC",
            "alarma": "SIN_ALARMA",
            "tiene_piscina": False,
            "alquiler_vacacional": False,
            "vivienda_rehabilitada": False,
            "numero_personas_vivienda": "3",
            "numero_habitaciones": "3",
        }
        for k, v in defaults.items():
            if k not in payload:
                payload[k] = v

    # 4. Create project in Merlin
    logger.info(f"[RETARIFICACION] Creating {ramo} project in Merlin for DNI: {dni}")
    result = create_merlin_project(payload)

    if result.get("success"):
        logger.info(f"[RETARIFICACION] Project created: ID={result.get('proyecto_id')}")
    else:
        logger.error(f"[RETARIFICACION] Failed: {result.get('error')}")

    return result
