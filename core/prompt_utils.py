"""Shared utilities for dynamic prompt assembly based on active agents config."""
import re


def filter_specialists(prompt: str, active_specialists: list[str], all_specialists: list[str]) -> str:
    """Remove prompt sections for disabled specialists and replace route options.

    Sections wrapped in [SPEC:name]...[/SPEC:name] markers are removed if
    the specialist is not in active_specialists. Markers for active specialists
    are stripped. The placeholder [ROUTE_OPTIONS] is replaced with a pipe-separated
    list of active specialist names.
    """
    disabled = set(all_specialists) - set(active_specialists)
    for name in disabled:
        prompt = re.sub(
            r'\[SPEC:' + re.escape(name) + r'\].*?\[/SPEC:' + re.escape(name) + r'\]',
            '',
            prompt,
            flags=re.DOTALL,
        )
    # Strip markers for active specialists
    for name in active_specialists:
        prompt = prompt.replace(f'[SPEC:{name}]', '')
        prompt = prompt.replace(f'[/SPEC:{name}]', '')

    # Replace route options placeholder
    active_in_order = [n for n in all_specialists if n in active_specialists]
    route_options = ' | '.join(f'"{n}"' for n in active_in_order)
    prompt = prompt.replace('[ROUTE_OPTIONS]', route_options)

    # Clean extra blank lines (3+ newlines → 2)
    prompt = re.sub(r'\n{3,}', '\n\n', prompt)
    return prompt
