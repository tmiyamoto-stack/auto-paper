from __future__ import annotations

import json

from audit.tier1.findings import Status, Severity
from .verdict import Verdict, validate_verdict, parse_verdict


def build_codex_command(prompt_path: str, artifact_path: str) -> list[str]:
    return ["codex", "exec", "--", prompt_path, artifact_path]


def _incomplete(finding_id: str, why: str) -> Verdict:
    return Verdict("codex", finding_id, Status.INCOMPLETE, Severity.CRITICAL, f"codex audit {why}")


def _extract_json_objects(text: str) -> list[dict]:
    """Extract all valid JSON objects from text using json.JSONDecoder.raw_decode.

    Iterates through the text looking for '{' characters, then uses raw_decode
    to attempt parsing a JSON object starting at that position. Valid dicts are
    collected and returned. This approach is O(n) and string-escape-aware via
    the standard library JSON parser.
    """
    dec = json.JSONDecoder()
    objs = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            # Not valid JSON starting here, skip this char and continue
            i += 1
            continue
        # Only collect if it's a dict (top-level object)
        if isinstance(obj, dict):
            objs.append(obj)
            i = end
        else:
            i += 1
    return objs


def run_codex_audit(prompt_path: str, artifact_path: str, finding_id: str, runner) -> Verdict:
    try:
        out = runner(build_codex_command(prompt_path, artifact_path))
    except Exception as e:  # noqa: BLE001 - any runner failure -> unauditable
        return _incomplete(finding_id, f"runner error: {e}")

    # Extract all valid JSON objects
    candidates = _extract_json_objects(out or "")

    # Iterate through candidates and find the LAST valid verdict
    last_valid_verdict = None
    for candidate in candidates:
        if not validate_verdict(candidate):  # empty list is falsy, meaning valid
            last_valid_verdict = candidate

    if last_valid_verdict is None:
        return _incomplete(finding_id, "unparseable (no valid verdict)")

    verdict = parse_verdict(last_valid_verdict)
    # Fix C: モデルの自己申告 identity は信頼しない。実際に起動したモデル・要求 finding_id を
    # 権威として上書きし、blinded は必ず True（盲検はハーネスが担保し自己申告しない）。
    verdict.model = "codex"
    verdict.finding_id = finding_id
    verdict.blinded = True
    return verdict
