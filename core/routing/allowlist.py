import json

from infra.config import get_routes_path

_ROUTES_PATH = get_routes_path()

def load_routes_config() -> dict:
    try:
        with open(_ROUTES_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_enabled_specialist_names(specialists) -> list[str]:
    """Get enabled specialist names from array or dict format."""
    if isinstance(specialists, list):
        return specialists  # Legacy array format: all enabled
    if isinstance(specialists, dict):
        return [name for name, cfg in specialists.items() if cfg.get("enabled", True)]
    return []


def get_active_specialists(domain: str, routes_config: dict = None) -> list[str]:
    """Return list of enabled specialist agent names for a domain."""
    if routes_config is None:
        routes_config = load_routes_config()
    domain_config = routes_config.get("domains", {}).get(domain, {})
    return _get_enabled_specialist_names(domain_config.get("specialists", {}))


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
        specialists = _get_enabled_specialist_names(domain.get("specialists", {}))
        if classifier:
            allowlist[classifier] = specialists
        # Allow specialists to route back to receptionist_agent (and aichat variant)
        for specialist in specialists:
            allowlist.setdefault(specialist, [
                "receptionist_agent",
                "aichat_receptionist_agent",
            ])

    # Explicit transitions from routes.json (e.g. aichat_receptionist_agent)
    for agent, targets in routes_config.get("transitions", {}).items():
        existing = allowlist.get(agent, [])
        allowlist[agent] = list(set(existing + targets))

    return allowlist
