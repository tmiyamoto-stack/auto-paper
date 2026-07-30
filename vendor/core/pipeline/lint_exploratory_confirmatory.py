from __future__ import annotations

import json

"""Structural linter enforcing explicit exploratory/confirmatory declaration.

Added 2026-07-28 in response to external review: when the same data is used
to explore an RQ and then to confirm/report it, unrecorded rejected analysis
branches make it impossible to tell exploratory work from confirmatory work
after the fact. `pipeline.manifest.capture_run_metadata()` added a
`rejected_branches` field for this, and `agents/01_design.md` step 3.5 now
instructs the design agent to report alternatives it considered and rejected.

This linter does not (and cannot) judge whether the *content* of
rejected_branches is honest or complete -- like lint_skill.py, it is a
structural check only: does the stage's manifest.json contain an explicit
`run_metadata.rejected_branches` declaration at all (even an empty list),
as opposed to the field being silently absent. An absent field means nobody
made the exploratory/confirmatory distinction visible; an empty list is an
explicit claim of "none considered", which is falsifiable in review and
therefore an improvement over silence.
"""

REQUIRED_PATH = ("run_metadata", "rejected_branches")


def lint_exploratory_confirmatory(manifest_path: str) -> list[str]:
    """Empty list == pass."""
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except FileNotFoundError:
        return [f"{manifest_path}: manifest not found"]
    except json.JSONDecodeError as e:
        return [f"{manifest_path}: manifest is not valid JSON ({e})"]

    node = manifest
    for key in REQUIRED_PATH:
        if not isinstance(node, dict) or key not in node:
            path_str = ".".join(REQUIRED_PATH)
            return [
                f"{manifest_path}: missing '{path_str}' -- design/analysis stage "
                "must explicitly declare rejected branches (even an empty list) "
                "via pipeline.manifest.capture_run_metadata(rejected_branches=...); "
                "silent absence is indistinguishable from 'nobody checked'."
            ]
        node = node[key]

    if not isinstance(node, list):
        return [f"{manifest_path}: run_metadata.rejected_branches must be a list, got {type(node).__name__}"]

    return []
