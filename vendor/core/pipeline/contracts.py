from __future__ import annotations

import json
import os

from . import schemas

STAGE_INPUTS: dict[str, list[tuple[str, object]]] = {
    "design": [],
    "variables": [("sap.md", None)],
    "analysis": [("variable_codebook.json", schemas.validate_variable_codebook)],
    "writing": [
        ("results.json", schemas.validate_results),
        ("methods_claims.json", schemas.validate_methods_claims),
        ("code_filters.json", schemas.validate_code_filters),
        ("flow.json", schemas.validate_flow),
    ],
}


def check_preconditions(stage: str, input_dir: str) -> list[str]:
    if stage not in STAGE_INPUTS:
        return [f"unknown stage: {stage}"]
    errs: list[str] = []
    for fname, validator in STAGE_INPUTS[stage]:
        path = os.path.join(input_dir, fname)
        if not os.path.isfile(path):
            errs.append(f"missing required input: {fname}")
            continue
        if validator is not None:
            try:
                with open(path, encoding="utf-8") as fh:
                    obj = json.load(fh)
            except (json.JSONDecodeError, OSError) as e:
                errs.append(f"{fname}: unreadable JSON ({e})")
                continue
            errs.extend(validator(obj))
    return errs
