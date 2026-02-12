"""Tool para crear proyectos de retarificación en Merlin Multitarificador."""

import json
import logging
from langchain.tools import tool
from services.merlin_client import create_merlin_project

logger = logging.getLogger(__name__)

# Fields that the agent MUST collect before calling this tool
_REQUIRED_FIELDS = ["dni", "matricula"]


@tool
def create_retarificacion_project_tool(data: str) -> dict:
    """
    Crea un proyecto de retarificación de seguro de auto en Merlin para comparar
    precios de múltiples aseguradoras.

    Input: JSON string con los datos del cliente y vehículo recopilados.

    Campos OBLIGATORIOS:
    - dni: str (NIF/DNI del tomador, ej: "12345678A")
    - matricula: str (matrícula del vehículo, ej: "1234ABC")

    Campos del tomador (recomendados):
    - nombre: str (nombre del tomador)
    - apellido1: str (primer apellido)
    - apellido2: str (segundo apellido)
    - fecha_nacimiento: str (formato "YYYY-MM-DD")
    - sexo: str ("MASCULINO" o "FEMENINO")
    - estado_civil: str ("SOLTERO", "CASADO", "VIUDO", "DIVORCIADO")
    - codigo_postal: str (5 dígitos)
    - poblacion: str (ciudad de residencia)
    - nombre_via: str (dirección completa)
    - id_provincia: str (código de 2 dígitos, ej: "03" para Alicante)
    - tipo_carnet: str (tipo de carnet, por defecto "B")
    - fecha_carnet: str (formato "YYYY-MM-DD")

            Campos del vehículo:
            - matricula: str (matrícula del vehículo, ej: "1234ABC")
            - tipo_de_garaje: str ("SIN_GARAJE", "INDIVIDUAL", "COLECTIVO", "PUBLICO")
            *Nota: Marca, modelo, combustible y fecha de matriculación se obtienen automáticamente vía DGT. No es necesario enviarlos aquí si ya se confirmaron con get_vehicle_info_dgt_tool.*

    Campos del historial asegurador (recomendados):
    - anos_asegurado: int (años totales con seguro)
    - aseguradora_actual: str (código DGS de la compañía actual)
    - siniestros: bool (si ha tenido siniestros)
    - anos_sin_siniestros: int (años sin siniestros)
    - fecha_efecto: str (formato "YYYY-MM-DD", fecha inicio nueva póliza)

    Returns:
        dict con resultado de la creación:
        - success: True/False
        - mongo_id: ID del proyecto en Merlin (si success)
        - id_pasarela: ID pasarela del proyecto (si success)
        - estado: estado del proyecto (si success)
        - num_aseguradoras: número de aseguradoras incluidas (si success)
        - error: mensaje de error (si no success)
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"success": False, "error": "Formato JSON inválido"}

    # Validate required fields
    missing = [f for f in _REQUIRED_FIELDS if not payload.get(f)]
    if missing:
        return {
            "success": False,
            "error": f"Campos obligatorios faltantes: {', '.join(missing)}",
        }

    logger.info(
        f"[RETARIFICACION] Creating project: dni={payload.get('dni')}, "
        f"matricula={payload.get('matricula')}, "
        f"marca={payload.get('marca', '?')} {payload.get('modelo', '?')}"
    )

    result = create_merlin_project(payload)

    if result.get("success"):
        logger.info(
            f"[RETARIFICACION] Project created: mongo_id={result.get('mongo_id')}, "
            f"{result.get('num_aseguradoras')} insurers"
        )
    else:
        logger.error(f"[RETARIFICACION] Failed: {result.get('error')}")

    return result
