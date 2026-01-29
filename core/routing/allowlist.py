import json

from core.config import get_routes_path

_ROUTES_PATH = get_routes_path()


def load_routes_config() -> dict:
    try:
        with open(_ROUTES_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def build_agent_allowlist(routes_config: dict) -> dict:
    allowlist = {}
    domains = routes_config.get("domains", {})
    # Solo dominios con enabled !== false (por defecto true)
    enabled_domains = [d for d in domains.values() if d.get("enabled", True)]

    classifiers = [
        domain.get("classifier")
        for domain in enabled_domains
        if domain.get("classifier")
    ]
    allowlist["receptionist_agent"] = classifiers

    for domain in enabled_domains:
        classifier = domain.get("classifier")
        specialists = domain.get("specialists", [])
        if classifier:
            allowlist[classifier] = specialists
        for specialist in specialists:
            allowlist.setdefault(specialist, [])

    return allowlist
