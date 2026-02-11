"""Retarificación tool - obtiene opciones de renovación para el cliente.
Actualmente hardcodeado; se conectará al ERP/cotizador real más adelante.
"""

import json
from langchain.tools import tool


@tool
def retarificacion_tool(data: str) -> dict:
    """
    Obtiene opciones de retarificación/renovación para una póliza del cliente.

    Args:
        data: JSON string con los datos necesarios. Campos esperados según ramo:
              - ramo: "auto" | "hogar" | "otros"
              AUTO: nombre, nif, fecha_nacimiento, codigo_postal, calle, fecha_carnet, matricula, numero_poliza_actual
              HOGAR: nombre, nif, fecha_nacimiento, direccion_tomador, direccion_vivienda
              Opcionalmente: datos extraídos por OCR (datos_ocr)

    Returns:
        dict con las opciones de renovación disponibles
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"error": "Formato JSON inválido", "status": "failed"}

    ramo = payload.get("ramo", "").lower()

    if ramo == "auto":
        return {
            "status": "success",
            "ramo": "auto",
            "cliente": payload.get("nombre", "Cliente"),
            "matricula": payload.get("matricula", "N/A"),
            "opciones": [
                {
                    "compania": "Mapfre",
                    "producto": "Terceros Ampliado",
                    "prima_anual": "385,00 €",
                    "coberturas": [
                        "Responsabilidad Civil Obligatoria",
                        "Responsabilidad Civil Voluntaria 50M",
                        "Defensa Jurídica",
                        "Asistencia en Viaje",
                        "Lunas",
                    ],
                    "tipo": "economica",
                },
                {
                    "compania": "Allianz",
                    "producto": "Todo Riesgo con Franquicia 300€",
                    "prima_anual": "520,00 €",
                    "coberturas": [
                        "Responsabilidad Civil Obligatoria",
                        "Responsabilidad Civil Voluntaria 50M",
                        "Defensa Jurídica",
                        "Asistencia en Viaje",
                        "Lunas",
                        "Robo",
                        "Incendio",
                        "Daños Propios (franquicia 300€)",
                    ],
                    "tipo": "intermedia",
                },
                {
                    "compania": "AXA",
                    "producto": "Todo Riesgo Sin Franquicia",
                    "prima_anual": "710,00 €",
                    "coberturas": [
                        "Responsabilidad Civil Obligatoria",
                        "Responsabilidad Civil Voluntaria 50M",
                        "Defensa Jurídica",
                        "Asistencia en Viaje Premium",
                        "Lunas",
                        "Robo",
                        "Incendio",
                        "Daños Propios sin franquicia",
                        "Vehículo de sustitución",
                    ],
                    "tipo": "premium",
                },
            ],
            "mensaje": "Se han encontrado 3 opciones de renovación.",
        }

    elif ramo == "hogar":
        return {
            "status": "success",
            "ramo": "hogar",
            "cliente": payload.get("nombre", "Cliente"),
            "direccion_vivienda": payload.get("direccion_vivienda", "N/A"),
            "opciones": [
                {
                    "compania": "Mapfre",
                    "producto": "Hogar Esencial",
                    "prima_anual": "195,00 €",
                    "coberturas": [
                        "Continente: 90.000 €",
                        "Contenido: 15.000 €",
                        "Responsabilidad Civil",
                        "Daños por agua",
                        "Incendio",
                    ],
                    "tipo": "economica",
                },
                {
                    "compania": "Zurich",
                    "producto": "Hogar Plus",
                    "prima_anual": "310,00 €",
                    "coberturas": [
                        "Continente: 120.000 €",
                        "Contenido: 30.000 €",
                        "Responsabilidad Civil",
                        "Daños por agua",
                        "Incendio",
                        "Robo",
                        "Asistencia hogar 24h",
                        "Defensa jurídica",
                    ],
                    "tipo": "intermedia",
                },
                {
                    "compania": "AXA",
                    "producto": "Hogar Premium",
                    "prima_anual": "430,00 €",
                    "coberturas": [
                        "Continente: 150.000 €",
                        "Contenido: 50.000 €",
                        "Responsabilidad Civil ampliada",
                        "Daños por agua",
                        "Incendio",
                        "Robo con atraco",
                        "Asistencia hogar 24h premium",
                        "Defensa jurídica",
                        "Daños estéticos",
                        "Jardín y piscina",
                    ],
                    "tipo": "premium",
                },
            ],
            "mensaje": "Se han encontrado 3 opciones de renovación.",
        }

    else:
        return {
            "status": "success",
            "ramo": ramo or "desconocido",
            "opciones": [],
            "mensaje": f"Ramo '{ramo}' no soportado aún para retarificación automática. Un gestor revisará tu caso.",
        }
