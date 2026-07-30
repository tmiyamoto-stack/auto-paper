from __future__ import annotations

from .findings import Finding, Status, Severity


def check_d(observed: dict[str, list], ranges: dict[str, tuple],
            impossible_ranges: dict[str, tuple] | None = None) -> list[Finding]:
    """値域外れ値監査。

    Fix3（Fable C3）: `ranges`（SAP 宣言のプラウジブル値域）だけでは severity が
    常に MAJOR になり、およそありえない値（臨床なら age=999/BP=0/負のラボ値、
    業務データなら負の売上/在庫 -1/負の所要時間）でも
    runner._critical_fail（CRITICAL のみ判定）が一切トリップしない欠陥があった。
    任意の `impossible_ranges`（SAP 宣言の絶対的にありえない境界）を渡すと、
    その境界外の値は CRITICAL FAIL に分離される。`impossible_ranges` 省略時
    （デフォルト None）は完全に従来の挙動（MAJOR のみ）を維持する。
    """
    findings: list[Finding] = []
    impossible_ranges = impossible_ranges or {}
    for name, values in observed.items():
        if name not in ranges:
            continue
        lo, hi = ranges[name]
        offenders = sorted({v for v in values if v is not None and not (lo <= v <= hi)})
        if not offenders:
            findings.append(Finding("D", Status.PASS, Severity.MAJOR,
                f"値域は妥当: {name}", f"{name} 範囲[{lo},{hi}]", variable=name))
            continue

        imp = impossible_ranges.get(name)
        if imp is not None:
            imp_lo, imp_hi = imp
            impossible_offenders = sorted({v for v in offenders if not (imp_lo <= v <= imp_hi)})
        else:
            impossible_offenders = []
        major_offenders = sorted(v for v in offenders if v not in impossible_offenders)

        if impossible_offenders:
            findings.append(Finding("D", Status.FAIL, Severity.CRITICAL,
                f"ありえない値: {name}",
                f"{name} 許容範囲[{imp_lo},{imp_hi}]外の値 {impossible_offenders}", variable=name))
        if major_offenders:
            findings.append(Finding("D", Status.FAIL, Severity.MAJOR,
                f"非現実値/外れ値: {name}",
                f"{name} 範囲[{lo},{hi}]外の値 {major_offenders}", variable=name))
    return findings
