from __future__ import annotations

from .findings import Finding, Status, Severity


def check_k(flow: dict, claimed_ns: dict[str, int]) -> list[Finding]:
    findings: list[Finding] = []
    stages = flow.get("stages", [])

    # Fix F: stages が空（検証すべき除外フローが無い）なら「N/フロー整合を検証不能」で
    # INCOMPLETE を返す。空 stages を暗黙 PASS にすると、フロー未定義のまま監査通過する
    # サイレント PASS になるため fail-closed 化する。
    if not stages:
        return [Finding("K", Status.INCOMPLETE, Severity.MAJOR,
            "除外フロー(stages)が空でN/フロー整合を検証不能",
            f"stages=0 claims={len(claimed_ns)}")]

    n_by_label = {s["label"]: s["n"] for s in stages}

    prev = None
    for s in stages:
        if prev is not None and s["n"] > prev:
            findings.append(Finding("K", Status.FAIL, Severity.MAJOR,
                "除外フローのNが増加している", f"stage '{s['label']}' n={s['n']} > 前段 {prev}"))
        prev = s["n"]

    for label in sorted(claimed_ns):
        want = claimed_ns[label]
        if label not in n_by_label:
            findings.append(Finding("K", Status.FAIL, Severity.MAJOR,
                "本文のN主張がフローに存在しない", f"label '{label}' claimed N={want} がflowに無い"))
        elif n_by_label[label] != want:
            findings.append(Finding("K", Status.FAIL, Severity.MAJOR,
                "本文のNとフローのNが不一致", f"'{label}': 本文={want} vs flow={n_by_label[label]}"))

    if not findings:
        findings.append(Finding("K", Status.PASS, Severity.MAJOR,
            "N/除外フロー整合", f"stages={len(stages)} claims={len(claimed_ns)}"))
    return findings
