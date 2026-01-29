"""Common utilities and hooks."""
import pathlib
from typing import Optional


def get_project_root() -> pathlib.Path:
    """Get the project root directory."""
    current_dir = pathlib.Path(__file__).parent

    markers = ['zoa_agents', 'requirements.txt', 'Dockerfile']

    for parent in [current_dir] + list(current_dir.parents):
        if any((parent / marker).exists() for marker in markers):
            return parent

    return current_dir.parent


def get_contracts_path(filename: str) -> pathlib.Path:
    """Get path to a contracts file."""
    return get_project_root() / "contracts" / filename


def get_routes_path() -> pathlib.Path:
    """Get path to routes configuration."""
    return get_project_root() / "routers" / "routes.json"


def get_config_path(filename: str = ".env") -> pathlib.Path:
    """Get path to a config file in the project root."""
    return get_project_root() / filename