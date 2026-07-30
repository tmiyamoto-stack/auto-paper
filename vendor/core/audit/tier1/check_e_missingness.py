"""Check E（欠測率↔Methods報告の照合）。

変数ごとの欠測率（データから算出＝プロファイラの n_empty/(n_empty+n_nonempty)＋
センチネル/欠損コード該当割合）を、Methods が欠測率と処理方針を報告した変数集合
（`reported_vars`）と突合する。閾値超の欠測を Methods で報告も処理方針も述べずに
解析すると、査読で最初に指摘される欠測バイアス（MAR/MNAR 未検討）を招く（DESIGN §9）。

Finding 契約は check_d/check_l と同一（check_id="E", 決定的・sorted）。severity は MAJOR
（欠測報告漏れは重大だが即棄却級の CRITICAL データ矛盾とは区別する）。

規則:
- `missing_rates is None`（欠測率算出不能） → 単一 INCOMPLETE/CRITICAL（監査不能、
  サイレント PASS 禁止）。
- 欠測率 > threshold かつ Methods 未報告（var not in reported_vars） → FAIL/MAJOR。
- 欠測率 > threshold かつ Methods 報告済 → PASS/MAJOR。
- 欠測率 <= threshold の変数 → フラグしない（finding 無し）。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity


def check_e_missingness(missing_rates: dict[str, float] | None,
                        reported_vars: set[str],
                        threshold: float = 0.05) -> list[Finding]:
    if missing_rates is None:
        return [Finding("E", Status.INCOMPLETE, Severity.CRITICAL,
            "欠測率の算出結果未提供で監査不能",
            "missing_rates=None")]

    reported_vars = reported_vars or set()
    findings: list[Finding] = []
    for var in sorted(missing_rates):
        rate = missing_rates[var]
        if rate <= threshold:
            continue
        if var not in reported_vars:
            findings.append(Finding("E", Status.FAIL, Severity.MAJOR,
                f"欠測率{rate:.1%}が閾値{threshold:.0%}超だがMethods未報告: {var}",
                f"欠測率{rate:.1%} 閾値{threshold:.0%} 変数={var}", variable=var))
        else:
            findings.append(Finding("E", Status.PASS, Severity.MAJOR,
                f"欠測率{rate:.1%}が閾値{threshold:.0%}超だがMethods報告済: {var}",
                f"欠測率{rate:.1%} 閾値{threshold:.0%} 変数={var}", variable=var))
    return findings
