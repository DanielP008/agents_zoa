"""Tools para tarificación en Merlin Multitarificador (Auto y Hogar).

Contiene cuatro herramientas:
  1. consulta_vehiculo_tool: Consulta DGT por matrícula (vía ERP).
  2. get_town_by_cp_tool: Obtiene población por código postal (vía ERP).
  3. consultar_catastro_tool: Consulta Catastro y calcula capitales (vía ERP).
  4. create_retarificacion_project_tool: Crea el proyecto final en Merlin (vía ERP).

NOTA: Estas herramientas llaman al webservice del ERP (ebroker-api) que centraliza la lógica.
"""

import json
import logging
from langchain.tools import tool
from services.erp_client import ERPClient

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS_AUTO = ["dni", "matricula", "fecha_efecto"]
_REQUIRED_FIELDS_HOGAR = ["dni", "codigo_postal", "fecha_efecto", "nombre_via", "numero_calle", "tipo_vivienda"]


# ============================================================================
# TOOL 1: Consulta de vehículo (DGT) - Solo AUTO
# ============================================================================

@tool
def consulta_vehiculo_tool(matricula: str, company_id: str) -> dict:
    """
    Consulta los datos técnicos de un vehículo en la DGT a partir de su matrícula.
    Devuelve marca, modelo, versión, combustible, garaje, km, fechas, etc.

    Usa esta herramienta en cuanto el cliente proporcione la matrícula.
    Muestra los datos al cliente en una LISTA DE PUNTOS y pregúntale si son correctos.

    Args:
        matricula: Matrícula del vehículo (ej: "3492GYW")
        company_id: ID de la compañía (se obtiene automáticamente del contexto)

    Returns:
        dict con los datos del vehículo recuperados de la DGT.
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
# TOOL 2: Consulta de población (CP) - Ambos ramos
# ============================================================================

@tool
def get_town_by_cp_tool(cp: str, company_id: str) -> dict:
    """
    Obtiene la población y provincia a partir de un código postal.

    Usa esta herramienta en cuanto el cliente proporcione el código postal.
    Muestra la población al cliente y pregúntale si es correcta.

    Args:
        cp: Código postal (ej: "28001")
        company_id: ID de la compañía (se obtiene automáticamente del contexto)

    Returns:
        dict con la población y provincia.
    """
    cp = cp.strip()
    logger.info(f"[GET_TOWN_BY_CP] Looking up CP: {cp}")
    
    client = ERPClient(company_id)
    result = client.merlin_get_town_by_cp(cp)
    
    if result.get("success"):
        logger.info(f"[GET_TOWN_BY_CP] Found: {result.get('poblacion')} ({result.get('descripcion_provincia')})")
    else:
        logger.error(f"[GET_TOWN_BY_CP] Failed: {result.get('error')}")
    return result


# ============================================================================
# TOOL 3: Consulta de Catastro (Hogar)
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
    Consulta los datos de una vivienda en el Catastro (superficie, año construcción, uso).

    Usa esta herramienta en cuanto el cliente proporcione la dirección completa en Hogar.
    Muestra los datos recuperados (año y superficie) al cliente y pregúntale si son correctos.

    Args:
        provincia: Nombre de la provincia (ej: "MADRID")
        municipio: Nombre del municipio/población (ej: "MADRID")
        tipo_via: Código del tipo de vía (CL, AV, PZ, PO, RD, CLZ, CM)
        nombre_via: Nombre de la vía (ej: "ALCALA")
        numero: Número de la vía (ej: "5")
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
        bloque: Bloque (opcional)
        escalera: Escalera (opcional)
        planta: Planta (ej: "5")
        puerta: Puerta (ej: "A")
        piso: Alias para planta (opcional)
        numero_personas: Número de personas en la vivienda (ej: "3")
        tipo_vivienda: Tipo de vivienda (PISO_EN_ALTO, PISO_EN_BAJO, ATICO, CHALET_O_VIVIENDA_UNIFAMILIAR, CHALET_O_VIVIENDA_ADOSADA)
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
        
        capital_continente = result.get("capital_continente", 0)
        capital_contenido = result.get("capital_contenido", 25000)
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
# TOOL 4: Creación de proyecto en Merlin (Auto o Hogar)
# ============================================================================

@tool
def create_retarificacion_project_tool(data: str, company_id: str) -> dict:
    """
    Crea un proyecto de tarificación de seguro (Auto o Hogar) en Merlin.
    Enriquece automáticamente los datos usando la DGT, el ERP, el Catastro y servicios de localización.
    
    Si la tarificación tiene éxito, devuelve el objeto 'proyecto' completo con las ofertas de las aseguradoras
    en el campo 'tarificaciones' o 'afinaciones'.

    Input: JSON string con los datos recopilados.

    Args:
        data: JSON string con todos los datos recopilados del cliente
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
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
    logger.info(f"[RETARIFICACION] Address: via={payload.get('nombre_via')}, num={payload.get('numero_calle')}, piso={payload.get('piso')}, puerta={payload.get('puerta')}")
    logger.info(f"[RETARIFICACION] Capitals: continente={payload.get('capital_continente')} (type={type(payload.get('capital_continente')).__name__}), contenido={payload.get('capital_contenido')} (type={type(payload.get('capital_contenido')).__name__})")
    
    client = ERPClient(company_id)
    result = client.merlin_create_project(payload)
    
    if result.get("success"):
        logger.info(f"[RETARIFICACION] Project created successfully: ID={result.get('proyecto_id')}, msg={result.get('mensaje')}")
    else:
        logger.error(f"[RETARIFICACION] FAILED: {result.get('error')}")
        logger.error(f"[RETARIFICACION] Full error result: {json.dumps(result, default=str, ensure_ascii=False)[:1000]}")

    return result
