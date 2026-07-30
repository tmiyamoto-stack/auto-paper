from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")


class UnresolvedPlaceholder(Exception):
    pass


class LeftoverPlaceholder(Exception):
    pass


def find_placeholders(template: str) -> list[str]:
    seen: list[str] = []
    for m in _PLACEHOLDER.finditer(template):
        key = m.group(1).strip()
        if key not in seen:
            seen.append(key)
    return seen


def _resolve(path: str, results: dict):
    node = results
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise UnresolvedPlaceholder(f"unresolved placeholder: {{{{{path}}}}}")
        node = node[part]
    return node


def render(template: str, results: dict) -> str:
    def sub(m: re.Match) -> str:
        return str(_resolve(m.group(1).strip(), results))

    out = _PLACEHOLDER.sub(sub, template)

    # Check for malformed/unresolved placeholders in the original template.
    # Compute the set of valid placeholder match start-offsets.
    valid_starts = {m.start() for m in _PLACEHOLDER.finditer(template)}

    # Find all {{ occurrences in the template
    pos = 0
    while True:
        pos = template.find("{{", pos)
        if pos == -1:
            break
        # If this {{ is not the start of a valid placeholder, it's malformed
        if pos not in valid_starts:
            raise LeftoverPlaceholder(f"malformed placeholder at offset {pos}: {template[pos:]}")
        pos += 1

    return out
