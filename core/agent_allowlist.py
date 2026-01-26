import json

from core.hooks import get_contracts_path

_ROUTES_PATH = get_contracts_path("routes.json")


def load_routes_config() -> dict:
    try:
        with open(_ROUTES_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def build_agent_allowlist(routes_config: dict) -> dict:
    allowlist = {}
    domains = routes_config.get("domains", {})

    # Receptionist can route to all domain classifiers
    classifiers = [
        domain.get("classifier")
        for domain in domains.values()
        if domain.get("classifier")
    ]
    allowlist["receptionist_agent"] = classifiers

    # Domain classifiers can route to specialists
    for domain in domains.values():
        classifier = domain.get("classifier")
        specialists = domain.get("specialists", [])
        if classifier:
            allowlist[classifier] = specialists
        for specialist in specialists:
            allowlist.setdefault(specialist, [])

    return allowlist
