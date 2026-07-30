"""Check L（打ち切り値/検出限界の未宣言・未処理検出）。

一次ソース = 自動データプロファイル（`pipeline.profile_data`）の
`censored_candidates`（列ごとの比較演算子接頭辞 "<5" や検出限界フレーズ
"検出せず" 等）。検出限界未満/以上の観測は「欠測」ではなく「情報を持つ
打ち切り観測」であり、実数値へ暗黙変換すると系統誤差になる（DESIGN §9）。

決定的規則（check_d/check_k と同じ Finding 契約, check_id="L", CRITICAL）:
- 打ち切り候補を持つ列が `declared_handled`（SAP/codebook が打ち切り処理方針
  ＝LOD 代入・Tobit・閾値処理等を宣言した列集合）に無い → FAIL（未宣言・未処理）。
- 宣言済み → PASS。
- `censored_by_column is None`（プロファイル未提供） → 単一 INCOMPLETE（監査不能、
  サイレント PASS 禁止）。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity


def check_l_censored(censored_by_column: dict[str, list] | None,
                     declared_handled: set[str]) -> list[Finding]:
    if censored_by_column is None:
        return [Finding("L", Status.INCOMPLETE, Severity.CRITICAL,
            "打ち切り値/検出限界のプロファイル未提供で監査不能",
            "censored_by_column=None")]

    declared_handled = declared_handled or set()
    findings: list[Finding] = []
    for col in sorted(censored_by_column):
        tokens = censored_by_column[col]
        if not tokens:
            continue
        toks = sorted(tokens)
        if col not in declared_handled:
            findings.append(Finding("L", Status.FAIL, Severity.CRITICAL,
                f"打ち切り値/検出限界が未宣言・未処理: {col}",
                f"例={toks}", variable=col))
        else:
            findings.append(Finding("L", Status.PASS, Severity.CRITICAL,
                f"打ち切り値/検出限界の処理方針が宣言済: {col}",
                f"例={toks}", variable=col))
    return findings
