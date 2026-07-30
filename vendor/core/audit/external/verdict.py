from __future__ import annotations

from dataclasses import dataclass

from audit.tier1.findings import Status, Severity

_STATUS = {s.value for s in Status}
_SEVERITY = {s.value for s in Severity}


@dataclass
class Verdict:
    model: str
    finding_id: str
    status: Status
    severity: Severity
    evidence: str
    blinded: bool = True


def validate_verdict(obj) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["verdict: must be object"]
    for key in ("model", "finding_id", "status", "severity", "evidence"):
        if not isinstance(obj.get(key), str):
            errs.append(f"verdict: missing/invalid '{key}'")
    if isinstance(obj.get("status"), str) and obj["status"] not in _STATUS:
        errs.append(f"verdict.status: must be one of {sorted(_STATUS)}")
    if isinstance(obj.get("severity"), str) and obj["severity"] not in _SEVERITY:
        errs.append(f"verdict.severity: must be one of {sorted(_SEVERITY)}")
    return errs


def parse_verdict(obj: dict) -> Verdict:
    return Verdict(
        model=obj["model"],
        finding_id=obj["finding_id"],
        status=Status(obj["status"]),
        severity=Severity(obj["severity"]),
        evidence=obj["evidence"],
        blinded=bool(obj.get("blinded", True)),
    )
