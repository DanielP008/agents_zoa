"""Tool to get vehicle information from DGT via Merlin."""

import logging
from langchain.tools import tool
from services.merlin_client import get_vehicle_info_by_matricula

logger = logging.getLogger(__name__)


@tool
def get_vehicle_info_dgt_tool(matricula: str) -> dict:
    """
    Consulta los datos técnicos de un vehículo en la DGT usando su matrícula.

    Input:
    - matricula: str (ej: "1234ABC")

    Returns:
        dict con los datos encontrados:
        - success: True/False
        - vehiculo: dict con marca, modelo, version, combustible,
          combustible_descripcion, fecha_matriculacion, cilindrada,
          potencia_cv, precio_vp, descripcion_completa, ids Base7, etc.
        - error: mensaje de error si falla

    Cuando success=True, muestra los datos principales al usuario:
    Marca, Modelo, Versión, Combustible y Fecha de matriculación.
    Pregúntale si son correctos antes de continuar.
    """
    matricula = matricula.strip().upper()
    logger.info(f"[DGT] Looking up vehicle: {matricula}")
    result = get_vehicle_info_by_matricula(matricula)

    if result.get("success"):
        v = result.get("vehiculo", {})
        logger.info(
            f"[DGT] Found: {v.get('marca')} {v.get('modelo')} "
            f"({v.get('version')}) - {v.get('combustible_descripcion')}"
        )
        # Ensure the LLM sees all relevant fields in the tool output
        return {
            "success": True,
            "datos_vehiculo": {
                "Marca": v.get("marca"),
                "Modelo": v.get("modelo"),
                "Versión": v.get("version"),
                "Combustible": v.get("combustible_descripcion"),
                "Fecha de Matriculación": v.get("fecha_matriculacion"),
                "Kilómetros Anuales": v.get("km_anuales"),
                "Kilómetros Totales": v.get("km_totales"),
                "Garaje": v.get("garaje")
            }
        }
    else:
        logger.error(f"[DGT] Failed: {result.get('error')}")
        return result
