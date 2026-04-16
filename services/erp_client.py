"""ERP client with backward-compatible function wrappers."""

import time
import logging
import os
import json
from typing import Optional, Dict, Any

from services.interfaces.erp_interfaces import (
    ERPBaseInterface,
    ERPClientError,
    CustomerInterface,
    PoliciesInterface,
    ReceiptsInterface,
    ClaimsInterface,
    RefundsInterface,
)

def _get_company_config_lazy(company_id: str):
    """Lazy import to avoid circular dependency."""
    from core.firebase_db import get_company_config
    return get_company_config(company_id)

logger = logging.getLogger(__name__)

# =============================================================================
# In-process policy cache (TTL-based, avoids repeated ERP calls per session)
# =============================================================================
_POLICY_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}  # key -> (timestamp, result)
_POLICY_CACHE_TTL = 300  # 5 minutes


def _cache_key(company_id: str, nif: str, ramo: Optional[str]) -> str:
    return f"{company_id}:{nif}:{ramo or '*'}"


def _get_cached_policies(key: str) -> Optional[Dict[str, Any]]:
    entry = _POLICY_CACHE.get(key)
    if entry is None:
        return None
    ts, result = entry
    if time.time() - ts > _POLICY_CACHE_TTL:
        del _POLICY_CACHE[key]
        return None
    logger.info(f"[ERP_CACHE] HIT for {key}")
    return result


def _set_cached_policies(key: str, result: Dict[str, Any]):
    _POLICY_CACHE[key] = (time.time(), result)

# =============================================================================
# Legacy ERPClient (backward compatibility)
# =============================================================================

class ERPClient(ERPBaseInterface):
    """Legacy client maintaining backward compatibility."""

    def get_client_policies_with_phones(
        self,
        nif: str,
        ramo: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get active policies with assistance phones for a specific category (ramo).
        Uses option='get_policies' which returns: number, company_id, company_name, risk, phones
        """
        # 1. Check company config for Excel ERP type
        try:
            company_config = _get_company_config_lazy(self.company_id) or {}
            erp_config = company_config.get('erp', {})
            erp_type = erp_config.get('erp_type', '').lower().strip()
            
            if erp_type == 'excel':
                excel_url = erp_config.get('url')
                if not excel_url:
                    logger.error(f"[ERP_CLIENT] Excel ERP type but no URL for {self.company_id}")
                else:
                    return self._get_policies_from_excel(nif, ramo, excel_url)
        except Exception as e:
            logger.error(f"[ERP_CLIENT] Error checking Excel ERP config: {e}")

        # 2. Fallback to standard ERP/Cache flow
        key = _cache_key(self.company_id, nif, ramo)
        cached = _get_cached_policies(key)
        if cached is not None:
            return cached

        interface = PoliciesInterface(self.company_id)
        result, status = interface.get_policies(nif, lines=ramo)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "policies": []
            }

        if isinstance(result, list):
            response = {"success": True, "policies": result}
        else:
            response = {"success": True, "policies": result if result else []}

        # Cache successful results
        if response.get("success"):
            _set_cached_policies(key, response)

        return response

    def _get_policies_from_excel(self, nif: str, ramo: Optional[str], url: str) -> Dict[str, Any]:
        """Fetch policies from a public CSV/Excel URL and filter by NIF."""
        try:
            import requests
            
            # 1. Transform Google Sheets URL to CSV export if needed
            if "docs.google.com/spreadsheets" in url and "/export" not in url:
                if "/edit" in url:
                    url = url.split("/edit")[0] + "/export?format=csv"
                else:
                    url = url.rstrip("/") + "/export?format=csv"
                logger.info(f"[ERP_EXCEL] Transformed Google Sheets URL to: {url}")

            logger.info(f"[ERP_EXCEL] Fetching data from {url} for NIF {nif}")
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"[ERP_EXCEL] Error fetching Excel: {response.status_code}")
                return {"success": False, "error": f"Error fetching Excel: {response.status_code}", "policies": []}
            
            # Normalize NIF for comparison (Numbers-Letter)
            clean_nif = nif.replace("-", "").replace(" ", "").strip().upper()
            if len(clean_nif) > 1 and clean_nif[-1].isalpha():
                formatted_nif = f"{clean_nif[:-1]}-{clean_nif[-1]}"
            else:
                formatted_nif = clean_nif

            lines = response.text.splitlines()
            found_company = None
            
            first_line = lines[0] if lines else ""
            delimiter = ';' if ';' in first_line else ','
            logger.info(f"[ERP_EXCEL] CSV lines={len(lines)}, delimiter='{delimiter}', first_line_preview='{first_line[:80]}'")
            
            for line in lines:
                if not line.strip(): continue
                parts = [p.strip().strip('"') for p in line.split(delimiter)]
                if len(parts) >= 2:
                    # Search NIF in ALL columns of the row
                    for cell in parts:
                        cell_clean = cell.replace(" ", "").replace("-", "").upper()
                        if cell_clean == clean_nif:
                            found_company = parts[1]  # Column B (index 1)
                            logger.info(f"[ERP_EXCEL] MATCH! Company='{found_company}' for NIF {clean_nif}. Row preview: {parts[:3]}")
                            break
                    if found_company:
                        break
            
            if not found_company:
                logger.warning(f"[ERP_EXCEL] No company found for NIF {formatted_nif} in Excel")
                return {"success": True, "policies": []}

            # 2. Load insurance phones from flow-erp
            phones_data = self._load_insurance_phones()
            
            # Normalize company name for lookup
            lookup_name = found_company.lower().strip()
            # Remove accents and special chars
            import unicodedata
            lookup_name = "".join(c for c in unicodedata.normalize('NFD', lookup_name) if unicodedata.category(c) != 'Mn')
            lookup_name = lookup_name.replace(" ", "_").replace(".", "").replace(",", "")
            
            # Special mapping for common names and variants
            mapping = {
                "catalana": "catalana_occidente",
                "occident": "catalana_occidente",
                "mutua": "mutua_madrilena",
                "fiatc": "fiatc",
                "mapfre": "mapfre",
                "mapfrevid": "mapfre",
                "mapfrefam": "mapfre",
                "axa": "axa",
                "reale": "reale",
                "generali": "generali",
                "zurich": "zurich",
                "liberty": "liberty",
                "pelayo": "pelayo",
                "helvetia": "helvetia",
                "ocaso": "ocaso",
                "santa_lucia": "santa_lucia",
                "sanitas": "sanitas",
                "adeslas": "adeslas",
                "asisa": "asisa",
                "dkv": "dkv"
            }
            
            # Try exact match in mapping first
            found_mapped = False
            for key, val in mapping.items():
                if key == lookup_name:
                    lookup_name = val
                    found_mapped = True
                    break
            
            # If not exact match, try if mapping key is contained in lookup_name (e.g. 'mapfrevid' contains 'mapfre')
            if not found_mapped:
                for key, val in mapping.items():
                    if key in lookup_name:
                        lookup_name = val
                        found_mapped = True
                        break

            phones = phones_data.get(lookup_name, {})
            if not phones:
                # Try partial match in phones_data keys
                for key in phones_data:
                    if key in lookup_name or lookup_name in key:
                        phones = phones_data[key]
                        logger.info(f"[ERP_EXCEL] Partial match found for '{found_company}' -> '{key}'")
                        break

            if not phones:
                logger.warning(f"[ERP_EXCEL] No phones found for company '{found_company}' (lookup: '{lookup_name}')")

            policy = {
                "number": "POL-EXCEL",
                "company_name": found_company.upper(),
                "risk": ramo or "GENERAL",
                "phones": phones
            }
            
            return {"success": True, "policies": [policy]}

        except Exception as e:
            logger.error(f"[ERP_EXCEL] Error processing Excel/Phones: {e}")
            return {"success": False, "error": str(e), "policies": []}

    def _load_insurance_phones(self) -> Dict[str, Any]:
        """Load insurance_phones.json from flow-erp. Tries multiple sources in order:
        1. ERP endpoint (cloud)
        2. Docker volume mount (/zoa_flow_erp/)
        3. Local sibling directory (development)
        """
        # 1. Try ERP endpoint (works in cloud after deploy)
        try:
            from services.interfaces.erp_interfaces import ERPBaseInterface
            erp_base = ERPBaseInterface(self.company_id)
            data = erp_base._make_request({
                "company_id": self.company_id,
                "option": "get_insurance_phones"
            })
            if isinstance(data, dict) and "error" not in data and len(data) > 0:
                logger.info(f"[ERP_EXCEL] Loaded {len(data)} companies from ERP endpoint")
                return data
        except Exception as e:
            logger.warning(f"[ERP_EXCEL] ERP endpoint unavailable: {e}")

        # 2. Try Docker volume mount
        for path in [
            "/zoa_flow_erp/insurance_phones.json",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../zoa_flow_erp/insurance_phones.json")),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    logger.info(f"[ERP_EXCEL] Loaded {len(data)} companies from {path}")
                    return data
                except Exception as e:
                    logger.warning(f"[ERP_EXCEL] Failed to read {path}: {e}")

        logger.error("[ERP_EXCEL] Could not load insurance_phones.json from any source")
        return {}

    def get_client_details(self, nif: str) -> Dict[str, Any]:
        """
        Get client details from the ERP.
        Uses option='detalle_cliente' which returns: id, legal_id, name, surname1, phone, email, address
        """
        interface = CustomerInterface(self.company_id)
        result, status = interface.get_details(nif)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "client": None
            }

        return {"success": True, "client": result}

    def get_policy_document(self, num_poliza: str) -> Dict[str, Any]:
        """
        Get a policy document from the ERP.
        Uses option='get_doc_policies' which returns: description, filename, data (Base64)
        """
        interface = PoliciesInterface(self.company_id)
        result, status = interface.get_document(num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "documents": []
            }

        # Result is a single document object, wrap in list for consistency
        if isinstance(result, dict) and "data" in result:
            return {"success": True, "documents": [result]}
        
        return {"success": True, "documents": result if result else []}

    def get_receipt_document(self, num_poliza: str) -> Dict[str, Any]:
        """
        Get the most recent receipt document for a policy.
        Uses option='documento_recibo' which returns: description, filename, data (Base64)
        """
        interface = ReceiptsInterface(self.company_id)
        result, status = interface.get_document(num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "receipt": {}
            }

        return {"success": True, "receipt": result if result else {}}

    def get_bank_info_for_refund(self, num_poliza: str) -> Dict[str, Any]:
        """Get bank account information for a refund."""
        interface = RefundsInterface(self.company_id)
        result, status = interface.get_bank_info(num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "account_number": None
            }

        return {"success": True, "account_number": result}

    def get_client_claims(self, nif: str) -> Dict[str, Any]:
        """
        Get all claims for a client.
        Uses option='get_claims' which returns: id, opening_date, risk, status
        """
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_claims(nif)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "claims": []
            }

        if isinstance(result, list):
            return {"success": True, "claims": result}

        return {"success": True, "claims": result if result else []}

    def get_claim_by_risk(self, nif: str, risk: str) -> Dict[str, Any]:
        """
        Get claim by risk identifier.
        Uses option='get_claim_by_risk' which returns: id, opening_date, risk, status
        """
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_claim_by_risk(nif, risk)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "claim": None
            }

        return {"success": True, "claim": result}

    def get_claim_status(self, id_siniestro: int) -> Dict[str, Any]:
        """
        Get status of a specific claim by ID.
        Uses option='get_status_claims' which returns: Status
        """
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_status(id_siniestro)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "status": None
            }

        return {"success": True, "status": result.get("Status")}

    def get_policy_by_num(self, num_poliza: str) -> Dict[str, Any]:
        """Get full policy details by policy number."""
        interface = PoliciesInterface(self.company_id)
        result, status = interface.get_policy_by_num(num_poliza)
        if status != 200 or "error" in result:
            return {"success": False, "error": result.get("error", "Unknown error"), "policy": None}
        return {"success": True, "policy": result}

    def get_policy_siniestralidad(self, num_poliza: str) -> Dict[str, Any]:
        """Get siniestralidad (claims history) data from a policy for Merlin tarification.

        Calls get_policy_by_num and extracts anos_asegurado, anos_compania,
        anos_sin_siniestros from the response.
        """
        result = self.get_policy_by_num(num_poliza)
        if not result.get("success"):
            return result

        policy = result.get("policy", {})
        logger.info(f"[ERP] Policy keys for siniestralidad extraction: {list(policy.keys())}")
        logger.info(f"[ERP] Full policy response (siniestralidad): {policy}")

        siniestralidad = _extract_siniestralidad(policy)
        logger.info(f"[ERP] Extracted siniestralidad: {siniestralidad}")
        return {"success": True, "siniestralidad": siniestralidad, "policy": policy}

    def get_policy_by_risk(self, nif: str, risk: str) -> Dict[str, Any]:
        """Find a policy by risk (e.g. matricula) for AUTOS ramo."""
        result = self.get_client_policies_with_phones(nif, ramo="AUTOS")
        if not result.get("success"):
            return result
        policies = result.get("policies", [])
        for p in policies:
            p_risk = str(p.get("risk", "")).strip().upper()
            if p_risk == risk.strip().upper():
                return self.get_policy_by_num(p.get("number"))
        return {"success": False, "error": f"No se encontró ninguna póliza activa para el riesgo {risk}", "policy": None}

    # --- Merlin / Retarificacion Methods ---
    
    def merlin_consulta_vehiculo(self, matricula: str) -> Dict[str, Any]:
        """Consulta DGT por matrícula."""
        from services.interfaces.erp_interfaces import MerlinInterface
        interface = MerlinInterface(self.company_id)
        result, status = interface.consulta_vehiculo(matricula)
        return result

    def merlin_get_town_by_cp(self, cp: str) -> Dict[str, Any]:
        """Obtiene población por CP."""
        from services.interfaces.erp_interfaces import MerlinInterface
        interface = MerlinInterface(self.company_id)
        result, status = interface.get_town_by_cp(cp)
        return result

    def merlin_consultar_catastro(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Consulta Catastro y calcula capitales."""
        from services.interfaces.erp_interfaces import MerlinInterface
        interface = MerlinInterface(self.company_id)
        result, status = interface.consultar_catastro(data)
        return result

    def merlin_create_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Crea proyecto en Merlin."""
        from services.interfaces.erp_interfaces import MerlinInterface
        interface = MerlinInterface(self.company_id)
        # Ensure company_id is present in the payload
        data["company_id"] = self.company_id
        result, status = interface.create_project(data)
        return result

    def merlin_finalizar_proyecto_hogar(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Finaliza proyecto HOGAR con capitales elegidos y lanza tarificación."""
        from services.interfaces.erp_interfaces import MerlinInterface
        interface = MerlinInterface(self.company_id)
        # Ensure company_id is present in the payload if needed by the ERP
        data["company_id"] = self.company_id
        result, status = interface.finalizar_proyecto_hogar(data)
        return result


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================

def _extract_siniestralidad(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Extract siniestralidad fields from a policy response.

    Tries several common field-name conventions used by eBroker.
    Returns a dict with keys: anos_asegurado, anos_compania, anos_sin_siniestros.
    Values default to None when not found so the caller can decide on defaults.
    """
    def _find(obj: Any, candidates: list[str]) -> Any:
        if not isinstance(obj, dict):
            return None
        for key in candidates:
            if key in obj:
                return obj[key]
        for val in obj.values():
            if isinstance(val, dict):
                found = _find(val, candidates)
                if found is not None:
                    return found
        return None

    anos_asegurado = _find(policy, [
        "anos_asegurado", "anos_asegurados", "years_insured",
        "total_anos_asegurado", "totalAnosAsegurado",
        "aniosAsegurado", "anios_asegurado",
    ])
    anos_compania = _find(policy, [
        "anos_compania", "anos_compania_anterior", "years_company",
        "years_previous_company", "anosCompania", "aniosCompania",
        "anios_compania",
    ])
    anos_sin_siniestros = _find(policy, [
        "anos_sin_siniestros", "years_no_claims", "years_without_claims",
        "anosSinSiniestros", "aniosSinSiniestros", "anios_sin_siniestros",
    ])

    return {
        "anos_asegurado": anos_asegurado,
        "anos_compania": anos_compania,
        "anos_sin_siniestros": anos_sin_siniestros,
    }


def get_assistance_phones_from_erp(
    nif: str,
    ramo: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch assistance phone numbers for active policies."""
    client = ERPClient(company_id)
    return client.get_client_policies_with_phones(nif, ramo=ramo)

def get_client_info_from_erp(
    nif: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch client details from the ERP."""
    client = ERPClient(company_id)
    return client.get_client_details(nif)

def get_client_policys(
    nif: str,
    ramo: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch client policies for the provided ramo."""
    client = ERPClient(company_id)
    result = client.get_client_policies_with_phones(nif, ramo=ramo)
    if not result.get("success"):
        return result
    return {"success": True, "policies": result.get("policies", [])}

def get_policy_document_from_erp(
    policy_number: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch a policy document from ERP by policy number."""
    client = ERPClient(company_id)
    return client.get_policy_document(policy_number)

def get_claims_from_erp(
    nif: str,
    company_id: str
) -> Dict[str, Any]:
    """
    Fetch claims (siniestros) for a NIF from ERP.
    Returns: id, opening_date, risk, status
    """
    client = ERPClient(company_id)
    result = client.get_client_claims(nif)

    if not result.get("success"):
        return result

    # Normalize response format
    claims = []
    for c in result.get("claims", []):
        claims.append({
            "id_claim": str(c.get("id", "")),
            "riesgo": c.get("risk", ""),
            "date": c.get("opening_date", ""),
            "status": c.get("status", ""),
        })
    return {"success": True, "claims": claims}

def get_claim_by_risk_from_erp(
    nif: str,
    risk: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch a specific claim by risk identifier."""
    client = ERPClient(company_id)
    return client.get_claim_by_risk(nif, risk)

def get_claim_status_from_erp(
    id_siniestro: int,
    company_id: str
) -> Dict[str, Any]:
    """Fetch status of a specific claim by ID."""
    client = ERPClient(company_id)
    return client.get_claim_status(id_siniestro)

def get_policy_by_risk_from_erp(
    nif: str,
    risk: str,
    company_id: str
) -> Dict[str, Any]:
    """Find a policy by risk (e.g. matricula) in the ERP."""
    client = ERPClient(company_id)
    return client.get_policy_by_risk(nif, risk)

def get_policy_siniestralidad_from_erp(
    num_poliza: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch siniestralidad data (anos_asegurado, anos_compania, anos_sin_siniestros)
    from the ERP for a given policy number."""
    client = ERPClient(company_id)
    return client.get_policy_siniestralidad(num_poliza)
