import json

from core.hooks import get_routes_path

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

    classifiers = [
        domain.get("classifier")
        for domain in domains.values()
        if domain.get("classifier")
    ]
    allowlist["receptionist_agent"] = classifiers

    for domain in domains.values():
        classifier = domain.get("classifier")
        specialists = domain.get("specialists", [])
        if classifier:
            allowlist[classifier] = specialists
        for specialist in specialists:
            allowlist.setdefault(specialist, [])

    return allowlist
