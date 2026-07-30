from __future__ import annotations

from .findings import Finding, Status, Severity


def check_j(labels_by_wave: dict[str, dict[str, list[str]]]) -> list[Finding]:
    findings: list[Finding] = []
    for qcode in sorted(labels_by_wave):
        by_wave = labels_by_wave[qcode]
        if len(by_wave) < 2:
            continue
        waves = sorted(by_wave)
        ref_wave = waves[0]
        ref = by_wave[ref_wave]
        mismatches = [w for w in waves[1:] if by_wave[w] != ref]
        if mismatches:
            detail = "; ".join(f"{w}={by_wave[w]}" for w in [ref_wave] + mismatches)
            findings.append(Finding("J", Status.FAIL, Severity.CRITICAL,
                f"波間で選択肢ラベルが不一致: {qcode}", detail, variable=qcode))
        else:
            findings.append(Finding("J", Status.PASS, Severity.CRITICAL,
                f"波間ハーモナイゼーション整合: {qcode}", f"waves={waves}", variable=qcode))
    return findings
