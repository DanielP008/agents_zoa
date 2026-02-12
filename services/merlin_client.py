"""Merlin Multitarificador API client.

Creates auto insurance projects in Merlin and launches multi-insurer pricing.
API Docs: https://drseguros.merlin.insure/multi/multitarificador4-servicios/doc.html

Flow:
  1. POST /login                         -> JWT token
  2. GET  /aseguradoras?subramo=...      -> Available insurer templates
  3. GET  /proyecto/nuevo?ids...         -> In-memory project template
  4. Fill datos_basicos (vehiculo, tomador, conductor, historial)
  5. PUT  /proyecto                      -> Save project to DB
"""

import os
import logging
import requests
from typing import Dict, Any, Optional, List

from core.timing import Timer, get_current_agent

logger = logging.getLogger(__name__)

SUBRAMO = "AUTOS_PRIMERA"
DATOS_BASICOS_CLASS = "ebroker.multi4.data.proyectos.autos1.DatosBasicosAutos1"


# =============================================================================
# Exceptions
# =============================================================================

class MerlinClientError(Exception):
    """Merlin API client error."""
    pass


# =============================================================================
# Helper builders (adapted from merlin.py)
# =============================================================================

def _parse_date(date_str: Optional[str]) -> Optional[List[int]]:
    """Convert 'YYYY-MM-DD' string to Merlin date format [YYYY, M, D]."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return [int(parts[0]), int(parts[1]), int(parts[2])]
    except (ValueError, IndexError):
        return None


def _build_vehiculo(data: dict) -> dict:
    """Build vehiculo dict for datos_basicos from collected data."""
    fecha_mat = _parse_date(data.get("fecha_matriculacion"))

    v: Dict[str, Any] = {
        "matricula": data.get("matricula", ""),
        "tipo_matricula": data.get("tipo_matricula", "ACTUAL"),
        "marca": data.get("marca", ""),
        "modelo": data.get("modelo", ""),
        "version": data.get("version", ""),
        "combustible": data.get("combustible", "G"),
        "km_actuales": data.get("km_actuales", 0),
        "km_anuales": data.get("km_anuales", 10000),
        "tipo_de_garaje": data.get("tipo_de_garaje", "COLECTIVO"),
        "precio_vp": data.get("precio_vp", 0),
        "pma": data.get("pma", 0),
        "cilindrada": data.get("cilindrada", 0),
        "potencia": data.get("potencia", 0),
        "accesorios": [],
    }

    if fecha_mat:
        v["fecha_matriculacion"] = fecha_mat
        v["fecha_primera_matriculacion"] = fecha_mat
        v["fecha_de_compra"] = fecha_mat

    # Technical IDs (optional – may come from vehicle lookup)
    for key in ("id_auto_base7", "id_tipo_base7", "id_categoria_base7", "id_clase_base7"):
        val = data.get(key)
        if val:
            v[key] = val

    return v


def _build_persona(data: dict, tipo_figura: str) -> dict:
    """Build persona dict for datos_basicos."""
    nombre = data.get("nombre", "")
    apellido1 = data.get("apellido1", "")
    apellido2 = data.get("apellido2", "")
    nombre_completo = f"{apellido1} {apellido2}, {nombre}".strip(", ")

    codigo_postal = data.get("codigo_postal", "")
    poblacion = data.get("poblacion", "")
    nombre_via = data.get("nombre_via", "")
    id_provincia = data.get("id_provincia", "")
    nacionalidad = data.get("nacionalidad", "108-6")

    p: Dict[str, Any] = {
        "numero_documento": data.get("dni", ""),
        "tipo_identificacion": data.get("tipo_identificacion", "NIF"),
        "sexo": data.get("sexo", "MASCULINO"),
        "estado_civil": data.get("estado_civil", "SOLTERO"),
        "tipo_figura": tipo_figura,
        "nacionalidad": nacionalidad,
        "zona_expedicion": nacionalidad,
        "codigo_postal": codigo_postal,
        "nombre_completo": nombre_completo,
        "lugar": poblacion,
        "cliente": {
            "tipo": "FISICA",
            "nombre": nombre,
            "apellido1": apellido1,
            "apellido2": apellido2,
            "nombre_completo": nombre_completo,
        },
        "direccion": {
            "id_pais": nacionalidad,
            "codigo_postal": codigo_postal,
            "id_tipo_via": data.get("id_tipo_via", "CL"),
            "nombre_via": nombre_via,
            "piso": data.get("piso", ""),
            "puerta": data.get("puerta", ""),
            "poblacion": poblacion,
            "id_provincia": id_provincia,
            "descripcion_provincia": data.get("descripcion_provincia", ""),
        },
    }

    fecha_nac = _parse_date(data.get("fecha_nacimiento"))
    if fecha_nac:
        p["fecha_nacimiento"] = fecha_nac

    p["tipo_carnet"] = data.get("tipo_carnet", "B")

    fecha_carnet = _parse_date(data.get("fecha_carnet"))
    if fecha_carnet:
        p["fecha_carnet"] = fecha_carnet

    if tipo_figura == "CONDUCTOR":
        p["is_innominada"] = False

    return p


def _build_historial(data: dict) -> dict:
    """Build historial_asegurador dict for datos_basicos."""
    fecha_efecto = _parse_date(data.get("fecha_efecto"))

    return {
        "fecha": fecha_efecto or [2026, 3, 1],
        "matricula": data.get("matricula", ""),
        "tipo_matricula": data.get("tipo_matricula", "ACTUAL"),
        "anos_asegurados": data.get("anos_asegurado", 0),
        "num_poliza": data.get("num_poliza", ""),
        "aseguradora_actual": data.get("aseguradora_actual", ""),
        "anos_compania": data.get("anos_compania", 0),
        "siniestros": data.get("siniestros", False),
        "anos_sin_siniestros": data.get("anos_sin_siniestros", 0),
        "datos_validos": True,
    }


# =============================================================================
# Merlin API Client
# =============================================================================

class MerlinClient:
    """Client for the Merlin Multitarificador API.

    Handles JWT authentication and the full project creation flow.
    Configuration is read from environment variables:
      - MERLIN_BASE_URL
      - MERLIN_USERNAME
      - MERLIN_PASSWORD
      - MERLIN_TIMEOUT (seconds, default 30)
    """

    def __init__(self):
        self.base_url = os.environ.get(
            "MERLIN_BASE_URL",
            "https://drseguros.merlin.insure/multi/multitarificador4-servicios",
        ).rstrip("/")
        # e-nfocar-services base URL (DGT vehicle lookup)
        self._enfocar_base_url = self.base_url.replace(
            "/multi/multitarificador4-servicios",
            "/e-nfocar-services",
        )
        self.username = os.environ.get("MERLIN_USERNAME", "")
        self.password = os.environ.get("MERLIN_PASSWORD", "")
        self.timeout = int(os.environ.get("MERLIN_TIMEOUT", "30"))
        self._session = requests.Session()
        self._token: Optional[str] = None

    # -- Internal helpers -------------------------------------------------

    def _ensure_config(self):
        """Validate that required config is present."""
        if not self.username or not self.password:
            raise MerlinClientError(
                "MERLIN_USERNAME and MERLIN_PASSWORD must be configured"
            )

    def _request(self, method: str, path: str, timer_label: str, **kwargs) -> Any:
        """Execute an HTTP request with timing and error handling."""
        url = f"{self.base_url}{path}"
        parent = get_current_agent()

        with Timer("merlin", timer_label, parent=parent):
            try:
                response = self._session.request(
                    method, url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                # Some endpoints return empty body
                if not response.content:
                    return {}
                return response.json()
            except requests.exceptions.Timeout:
                raise MerlinClientError(f"Timeout calling {timer_label}")
            except requests.exceptions.ConnectionError as exc:
                raise MerlinClientError(f"Connection error ({timer_label}): {exc}")
            except requests.exceptions.HTTPError as exc:
                body = ""
                if exc.response is not None:
                    body = exc.response.text[:300]
                raise MerlinClientError(
                    f"HTTP {exc.response.status_code if exc.response else '?'} "
                    f"on {timer_label}: {body}"
                )

    # -- Public API -------------------------------------------------------

    def login(self) -> str:
        """Authenticate and store JWT token. Returns the token string.

        Note: this does NOT use ``_request`` because we need access to
        the *response headers* (the JWT token is returned there, not in
        the response body).
        """
        self._ensure_config()
        logger.info("[MERLIN] Logging in...")

        parent = get_current_agent()
        with Timer("merlin", "merlin_login", parent=parent):
            try:
                resp = self._session.post(
                    f"{self.base_url}/login",
                    json={"username": self.username, "password": self.password},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except requests.exceptions.RequestException as exc:
                raise MerlinClientError(f"Login failed: {exc}")

        self._token = resp.headers.get("Authorization")
        if not self._token:
            raise MerlinClientError("No Authorization token received from Merlin")

        self._session.headers.update({
            "Authorization": self._token,
            "Content-Type": "application/json",
        })
        logger.info("[MERLIN] Login successful.")
        return self._token

    def obtener_aseguradoras(self, subramo: str = SUBRAMO) -> Dict[str, Any]:
        """Get available insurers and their active template IDs.

        Returns: { dgs: { nombre, plantilla_id, plantilla_nombre } }
        """
        logger.info(f"[MERLIN] Fetching insurers for '{subramo}'...")

        items = self._request(
            "GET",
            "/aseguradoras",
            "merlin_aseguradoras",
            params={"subramo": subramo},
        )

        aseguradoras: Dict[str, Any] = {}
        for item in items:
            dgs = item.get("id", "")
            nombre = item.get("nombre", "")
            plantillas = item.get("plantillas", [])
            activa = next(
                (p for p in plantillas if p.get("activa")),
                plantillas[0] if plantillas else None,
            )
            if activa:
                aseguradoras[dgs] = {
                    "nombre": nombre,
                    "plantilla_id": activa.get("id"),
                    "plantilla_nombre": activa.get("nombre"),
                }
        logger.info(f"[MERLIN] Found {len(aseguradoras)} insurers.")
        return aseguradoras

    def obtener_proyecto_nuevo(self, plantillas_ids: List[str]) -> Dict[str, Any]:
        """Get a new in-memory project template for the given insurer template IDs."""
        ids_str = ",".join(str(i) for i in plantillas_ids)
        logger.info(f"[MERLIN] Creating new project template (ids={ids_str[:60]}...)")

        proyecto = self._request(
            "GET",
            "/proyecto/nuevo",
            "merlin_proyecto_nuevo",
            params={"ids": ids_str},
        )

        logger.info(f"[MERLIN] Got project template with {len(proyecto.get('aseguradoras', []))} insurers.")
        return proyecto

    def guardar_proyecto(self, proyecto: Dict[str, Any]) -> Dict[str, Any]:
        """Save project to DB via PUT /proyecto."""
        logger.info("[MERLIN] Saving project...")
        result = self._request("PUT", "/proyecto", "merlin_guardar_proyecto", json=proyecto)
        logger.info(f"[MERLIN] Project saved. ID={result.get('id', 'unknown')}")
        return result

    def obtener_proyecto_por_id(self, proyecto_id: int) -> Dict[str, Any]:
        """Get a project by ID."""
        logger.info(f"[MERLIN] Fetching project {proyecto_id}...")
        return self._request("GET", f"/proyecto/{proyecto_id}", "merlin_get_proyecto")

    def actualizar_riesgo_autos(self, proyecto_id: int, riesgo: Dict[str, Any]) -> Dict[str, Any]:
        """Update the riesgoAutos section of a project."""
        logger.info(f"[MERLIN] Updating riesgoAutos for project {proyecto_id}...")
        return self._request(
            "PUT",
            f"/proyecto/{proyecto_id}/riesgoAutos",
            "merlin_update_riesgo",
            json=riesgo,
        )

    def crear_proyecto_completo(self, datos: dict) -> Dict[str, Any]:
        """Create a complete auto insurance project in Merlin.

        This is the main entry point: login -> insurers -> template -> fill -> save.
        """
        try:
            self.login()

            # Step 1: Get available insurers
            aseguradoras = self.obtener_aseguradoras()
            if not aseguradoras:
                return {"success": False, "error": "No insurers available"}

            plantillas_ids = [a["plantilla_id"] for a in aseguradoras.values()]

            # Step 2: Get a new project template
            proyecto = self.obtener_proyecto_nuevo(plantillas_ids)

            # Step 3: Fill datos_basicos
            datos_basicos = proyecto.get("datosBasicos") or proyecto.get("datos_basicos", {})

            datos_basicos["vehiculo"] = _build_vehiculo(datos)
            datos_basicos["tomador"] = _build_persona(datos, "TOMADOR")
            datos_basicos["conductor"] = _build_persona(datos, "CONDUCTOR")
            datos_basicos["historial_asegurador"] = _build_historial(datos)
            datos_basicos["@class"] = DATOS_BASICOS_CLASS

            # Set back on project (handle both camelCase and snake_case)
            if "datosBasicos" in proyecto:
                proyecto["datosBasicos"] = datos_basicos
            else:
                proyecto["datos_basicos"] = datos_basicos

            # Step 4: Save project
            result = self.guardar_proyecto(proyecto)

            return {
                "success": True,
                "proyecto_id": result.get("id"),
                "mensaje": f"Proyecto creado con {len(plantillas_ids)} aseguradoras",
                "num_aseguradoras": len(plantillas_ids),
            }

        except MerlinClientError as exc:
            logger.error(f"[MERLIN] Project creation failed: {exc}")
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception(f"[MERLIN] Unexpected error creating project: {exc}")
            return {"success": False, "error": f"Error inesperado: {exc}"}

    def consultar_dgt_por_matricula(self, matricula: str) -> Dict[str, Any]:
        """Consulta los datos del vehiculo en la DGT/Base7 directamente por matricula.

        Uses GET /e-nfocar-services/v1/vehiculos/{matricula}?categoria=1
        with Basic Auth (separate from multitarificador JWT).

        Returns:
            {"success": True, "vehiculo": {...}} o {"success": False, "error": "..."}
        """
        try:
            dgt_url = f"{self._enfocar_base_url}/v1/vehiculos/{matricula}"
            logger.info(f"[MERLIN] DGT lookup: {dgt_url}")

            # e-nfocar-services uses Basic Auth (ebroker:ebrokerPM),
            # NOT the multitarificador JWT token.
            enfocar_auth = (
                os.environ.get("ENFOCAR_USERNAME", "ebroker"),
                os.environ.get("ENFOCAR_PASSWORD", "ebrokerPM"),
            )

            parent = get_current_agent()
            with Timer("merlin", "merlin_dgt_lookup", parent=parent):
                try:
                    resp = requests.get(
                        dgt_url,
                        params={"categoria": "1"},
                        auth=enfocar_auth,
                        headers={"Accept": "application/json"},
                        timeout=self.timeout,
                    )
                    logger.info(
                        f"[MERLIN] DGT response status: {resp.status_code}"
                    )
                    resp.raise_for_status()
                    results = resp.json()
                except requests.exceptions.RequestException as exc:
                    raise MerlinClientError(f"DGT lookup failed: {exc}")

            # Response is an array of matching vehicles
            if not results or not isinstance(results, list) or len(results) == 0:
                logger.warning(f"[MERLIN] DGT returned no results for {matricula}")
                return {"success": False, "error": f"No se encontraron datos para la matricula {matricula}"}

            # Take the first (and usually only) result
            vehiculo = results[0]
            logger.info(f"[MERLIN] DGT raw response: {vehiculo}")
            
            # Use data from 'base7' if available, as it's more complete
            base7 = vehiculo.get("base7", {}) or {}
            
            logger.info(
                f"[MERLIN] DGT found: {base7.get('marca') or vehiculo.get('marca')} "
                f"{base7.get('modelo') or vehiculo.get('modelo')} "
                f"({base7.get('version') or vehiculo.get('version')})"
            )

            # Extract motor/combustible info
            motor = base7.get("motor", {}) or vehiculo.get("motor", {})
            combustible_id = motor.get("id", "") if isinstance(motor, dict) else ""
            combustible_desc = motor.get("descripcion", "") if isinstance(motor, dict) else ""

            # Extract Base7 IDs (needed for accurate pricing later)
            categoria = base7.get("categoria", {}) or {}
            tipo = base7.get("tipo", {}) or {}
            clase = base7.get("clase", {}) or {}

            # Extract additional vehicle data
            datos_adicionales = vehiculo.get("datosAdicionalesVehiculo", {}) or {}
            
            # Extract garage info if present
            garaje_info = datos_adicionales.get("garaje", {}) or {}
            garaje_desc = garaje_info.get("descripcion", "") if isinstance(garaje_info, dict) else ""

            return {
                "success": True,
                "vehiculo": {
                    "marca": base7.get("marca") or vehiculo.get("marca"),
                    "modelo": base7.get("modelo") or vehiculo.get("modelo"),
                    "version": base7.get("version") or vehiculo.get("version"),
                    "combustible": combustible_id,
                    "combustible_descripcion": combustible_desc,
                    "fecha_matriculacion": datos_adicionales.get("fechaMatriculacion") or base7.get("fechaMatriculacion") or vehiculo.get("fechaMatriculacion"),
                    "fecha_primera_matriculacion": datos_adicionales.get("fechaPrimeraMatriculacion") or base7.get("fechaPrimeraMatriculacion") or vehiculo.get("fechaPrimeraMatriculacion"),
                    "fecha_compra": datos_adicionales.get("fechaCompra") or base7.get("fechaCompra") or vehiculo.get("fechaCompra"),
                    "cilindrada": base7.get("cilindrada") or vehiculo.get("cilindrada"),
                    "potencia_cv": base7.get("cv") or vehiculo.get("cv"),
                    "precio_vp": base7.get("precioVp") or vehiculo.get("precioVp"),
                    "descripcion_completa": base7.get("descripcion") or vehiculo.get("descripcion"),
                    # Base7 IDs for project creation
                    "id_auto_base7": base7.get("id", ""),
                    "id_tipo_base7": tipo.get("id", ""),
                    "id_categoria_base7": categoria.get("id", ""),
                    "id_clase_base7": clase.get("idClase", ""),
                    # Additional data
                    "km_anuales": datos_adicionales.get("kilometrosAnuales"),
                    "km_totales": datos_adicionales.get("kilometrosTotales"),
                    "garaje": garaje_desc,
                },
            }

        except MerlinClientError as exc:
            logger.error(f"[MERLIN] DGT lookup failed: {exc}")
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.error(f"[MERLIN] DGT lookup unexpected error: {exc}")
            return {"success": False, "error": str(exc)}


# =============================================================================
# Wrapper functions for tools (same pattern as erp_client.py)
# =============================================================================

def create_merlin_project(datos: dict) -> Dict[str, Any]:
    """Create a complete Merlin auto insurance project.

    This is the main entry point used by the retarificacion tool.
    """
    client = MerlinClient()
    return client.crear_proyecto_completo(datos)


def get_vehicle_info_by_matricula(matricula: str) -> Dict[str, Any]:
    """Get vehicle info from DGT via Merlin e-nfocar-services."""
    client = MerlinClient()
    return client.consultar_dgt_por_matricula(matricula)
