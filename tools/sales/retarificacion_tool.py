"""Tools para retarificación en Merlin Multitarificador.

Contiene tres herramientas:
  1. consulta_vehiculo_tool: Consulta DGT por matrícula y muestra datos al cliente.
  2. get_town_by_cp_tool: Obtiene población por código postal.
  3. create_retarificacion_project_tool: Crea el proyecto final en Merlin.
"""

import json
import logging
from langchain.tools import tool
from services.merlin_client import create_merlin_project, get_vehicle_info_by_matricula, get_town_by_cp
from services.erp_client import get_policy_by_risk_from_erp

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ["dni", "matricula", "fecha_efecto"]


# ============================================================================
# TOOL 1: Consulta de vehículo (DGT)
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
            """Return 'No especificado' for empty/None values."""
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
# TOOL 2: Consulta de población (CP)
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
        logger.info(f"[GET_TOWN_BY_CP] Found: {result.get('poblacion')} ({result.get('provincia')})")
    else:
        logger.error(f"[GET_TOWN_BY_CP] Failed: {result.get('error')}")
    return result


# ============================================================================
# TOOL 3: Creación de proyecto en Merlin
# ============================================================================

@tool
def create_retarificacion_project_tool(data: str) -> dict:
    """
    Crea un proyecto de retarificación de seguro de auto en Merlin.
    Enriquece automáticamente los datos usando la DGT, el ERP y servicios de localización.

    Input: JSON string con los datos del cliente y vehículo recopilados.

    Campos OBLIGATORIOS:
    - dni: str (NIF/DNI del tomador)
    - matricula: str (matrícula del vehículo)
    - fecha_efecto: str (formato "YYYY-MM-DD", fecha inicio nueva póliza)

    Campos opcionales:
    - nombre, apellido1, apellido2, fecha_nacimiento, sexo, estado_civil,
      codigo_postal, fecha_carnet, company_id.
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"success": False, "error": "Formato JSON inválido"}

    missing = [f for f in _REQUIRED_FIELDS if not payload.get(f)]
    if missing:
        return {
            "success": False,
            "error": f"Campos obligatorios faltantes para retarificar: {', '.join(missing)}",
        }

    matricula = payload.get("matricula")
    dni = payload.get("dni")
    cp = payload.get("codigo_postal")

    # Enrich with DGT data
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
    else:
        logger.warning(f"[RETARIFICACION] DGT enrichment failed: {dgt_result.get('error')}")

    # Enrich with Town/CP data
    if cp:
        logger.info(f"[RETARIFICACION] Enriching town for CP {cp}")
        town_result = get_town_by_cp(cp)
        if town_result.get("success"):
            payload.update({
                "poblacion": town_result.get("poblacion"),
                "id_poblacion": town_result.get("id_poblacion"),
                "id_provincia": town_result.get("id_provincia"),
            })

    # Enrich with ERP data (Policy history)
    if dni and matricula:
        company_id = payload.get("company_id", "")
        if company_id:
            logger.info(f"[RETARIFICACION] Checking ERP for policy history (DNI={dni}, Risk={matricula})")
            erp_result = get_policy_by_risk_from_erp(dni, matricula, company_id)
            if erp_result.get("success"):
                policy = erp_result.get("policy", {})
                payload.update({
                    "aseguradora_actual": policy.get("company_name") or policy.get("company_id"),
                    "num_poliza": policy.get("number"),
                })

    # Create project in Merlin
    logger.info(f"[RETARIFICACION] Creating final project in Merlin for DNI: {dni}")
    result = create_merlin_project(payload)

    if result.get("success"):
        logger.info(f"[RETARIFICACION] Project created successfully: ID={result.get('proyecto_id')}")
    else:
        logger.error(f"[RETARIFICACION] Merlin project creation failed: {result.get('error')}")

    return result
