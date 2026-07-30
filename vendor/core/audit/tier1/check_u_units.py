"""Check U（単位宣言↔生理的値域の逸脱照合＝単位混在の検出）。

連続量の SAP 宣言単位（"%"/"mmol/mol"/"mg/dL"/"mmol/L" 等）と、その観測中央値が
宣言単位の生理的に妥当な中央値域に収まるかを決定的に照合する。HbA1c を "%" と
宣言しながら観測中央値が 40 なら実データは mmol/mol であり、単位取り違え/混在の
可能性が高い（DESIGN §9）。

Finding 契約は check_d/check_l と同一（check_id="U", 決定的・sorted）。severity は MAJOR。

規則（`declared_units` の各変数について）:
- `observed_center is None`、または当該変数が `observed_center` に無い → INCOMPLETE
  （観測値なしで照合不能、サイレント PASS 禁止）。
- 宣言単位が `plausible_by_unit` に無い（基準域未提供） → INCOMPLETE（照合不能）。
- 観測中央値が宣言単位の妥当域 [lo,hi] 外 → FAIL/MAJOR（単位不整合の疑い）。
- 妥当域内 → PASS/MAJOR。

宣言単位を持たない連続量は呼び出し側の責任（本 check は宣言済みのみ監査する）。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity


def check_u_units(declared_units: dict[str, str],
                  observed_center: dict[str, float] | None,
                  plausible_by_unit: dict[str, tuple]) -> list[Finding]:
    findings: list[Finding] = []
    for var in sorted(declared_units):
        unit = declared_units[var]
        if observed_center is None or var not in observed_center:
            findings.append(Finding("U", Status.INCOMPLETE, Severity.MAJOR,
                f"観測中央値なしで単位照合不能: {var}",
                f"宣言単位={unit} だが観測中央値未提供", variable=var))
            continue
        if unit not in plausible_by_unit:
            findings.append(Finding("U", Status.INCOMPLETE, Severity.MAJOR,
                f"単位の基準域未提供で照合不能: {var}",
                f"宣言単位={unit} の妥当域が plausible_by_unit に無い", variable=var))
            continue
        center = observed_center[var]
        lo, hi = plausible_by_unit[unit]
        if not (lo <= center <= hi):
            findings.append(Finding("U", Status.FAIL, Severity.MAJOR,
                f"単位不整合の疑い: {var}",
                f"単位不整合の疑い: {var} 宣言単位={unit} だが観測中央値={center}が"
                f"妥当域[{lo},{hi}]外（別単位取り違え/混在の可能性）", variable=var))
        else:
            findings.append(Finding("U", Status.PASS, Severity.MAJOR,
                f"単位と観測中央値は整合: {var}",
                f"宣言単位={unit} 観測中央値={center} 妥当域[{lo},{hi}]", variable=var))
    return findings
