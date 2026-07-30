from __future__ import annotations

from .findings import Finding, Status, Severity


def check_b(methods_claims: list[dict], code_filters: list[dict]) -> list[Finding]:
    findings: list[Finding] = []

    if not methods_claims and not code_filters:
        return [
            Finding("B", Status.INCOMPLETE, Severity.CRITICAL,
                    "Methods主張とコードフィルタが共に空で突合不能",
                    "methods_claims=[] code_filters=[]")
        ]

    implemented: dict[str, set[str]] = {}
    for f in code_filters:
        implemented.setdefault(f["procedure"], set()).update(f["applies_to"])

    # 方向1: 記載 → 実装
    for c in methods_claims:
        claimed = set(c["applies_to"])
        covered = implemented.get(c["procedure"], set())
        missing = claimed - covered
        if missing:
            findings.append(
                Finding("B", Status.FAIL, Severity.CRITICAL,
                        f"Methods記載の手続きがコード未適用: {c['procedure']}",
                        f"claim {c['id']}: 未適用 {sorted(missing)}")
            )
        else:
            findings.append(
                Finding("B", Status.PASS, Severity.CRITICAL,
                        f"手続きは記載通り適用: {c['procedure']}", f"claim {c['id']}")
            )

    # 方向2: 実装 → 記載
    claimed_procs = {c["procedure"] for c in methods_claims}
    for f in code_filters:
        if f["procedure"] not in claimed_procs:
            findings.append(
                Finding("B", Status.FAIL, Severity.MAJOR,
                        f"コードのフィルタがMethods未記載: {f['procedure']}", f.get("evidence", ""))
            )

    return findings
