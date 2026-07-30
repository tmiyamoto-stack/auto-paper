"""Check E 追加規則（欠測メカニズム宣言↔実装手法の突合）。

共同研究者レビュー指摘2-(2)。既存の `check_e_missingness`（欠測率↔Methods 報告）とは
別規則で、`rule_id="t1.missingness.mechanism_implementation"`。check_id は既存 "E" を
共有する（check_m / check_m_metadata と同じ前例）。

## 本チェックが保証するもの／保証しないもの（両レビューの一致点）

**保証する（決定的）**: 宣言と実装の**文字通りの整合**。SAP が MI を宣言したのに実行
trace が complete-case、という矛盾は機械的に検出できる。また「5%超の欠測を無宣言・
無処理で解析」も決定的な報告欠陥である。

**保証しない**: 「宣言されたメカニズムが真か」。MCAR/MAR/MNAR は観測データから確定
できない（原理的に検証不能）。したがって本チェックは**メカニズムの妥当性を判定しない**。

## 固定対応表を作らない理由（Codex Sol の反例）

「MAR なら MI、MCAR なら complete-case」という硬い対応表は誤検出を生む。共変量条件付き
MAR の下では、正しく指定した回帰／尤度解析の complete-case 推定は妥当でありうる
（White & Carlin 2010, Stat Med 29:2920）。よって MAR×complete-case は**無条件 FAIL に
せず**、`cc_covariate_only_justified` の宣言があれば PASS＋Tier2 送付とする。
逆に「MAR＋MI」と文字列が揃っていても、imputation model からアウトカムや補助変数が
落ちていれば欠陥である——それは本チェックでは捕まらない（Tier2/G0 の管轄）と明記する。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity

_RULE = "t1.missingness.mechanism_implementation"

_MECHANISMS = {"mcar", "mar", "mnar"}
_HANDLINGS = {
    "complete_case", "mi", "ipw_missing", "fiml", "single_imputation",
    "missing_indicator", "none",
}
# MNAR 宣言下で要求される感度分析の別名（delta 調整・pattern-mixture 等）。
_MNAR_OK_HANDLINGS = {"pattern_mixture", "delta_adjustment", "selection_model"}


_RULE_DECL = "t1.missingness.declared_vs_implemented"


def check_e_declared_vs_implemented(declared_handling: str | None,
                                    implemented_handling: str | None) -> list[Finding]:
    """SAP宣言の欠測処理手法と実行traceの**文字通りの突合**（check B と同格）。

    互換性の判断（MAR×complete-case が妥当かなど）は check_e_mechanism の担当で、
    そちらは正当な例外を持つため MAJOR。こちらは「MIを行うと宣言して complete-case を
    実行した」という手続きそのものの矛盾なので CRITICAL。
    """
    if declared_handling is None and implemented_handling is None:
        return []
    if declared_handling is None or implemented_handling is None:
        return [Finding("E", Status.INCOMPLETE, Severity.CRITICAL,
            "欠測処理の宣言↔実装突合が片側のみ供給されており監査不能",
            f"declared_handling={declared_handling!r}, "
            f"implemented_handling={implemented_handling!r}",
            rule_id=_RULE_DECL, taxonomy_id="E")]
    d = declared_handling.lower().strip()
    i = implemented_handling.lower().strip()
    if d != i:
        return [Finding("E", Status.FAIL, Severity.CRITICAL,
            "SAP宣言の欠測処理手法と実行traceが不一致",
            f"宣言={d}, 実装={i}（記載された手続きが実行されていない）",
            rule_id=_RULE_DECL, taxonomy_id="E")]
    return [Finding("E", Status.PASS, Severity.CRITICAL,
        "SAP宣言の欠測処理手法と実行traceは一致",
        f"handling={d}", rule_id=_RULE_DECL, taxonomy_id="E")]


def check_e_mechanism(declared_mechanism: str | None,
                      handling: str | None,
                      mnar_sensitivity: bool = False,
                      cc_covariate_only_justified: bool = False,
                      max_missing_rate: float | None = None,
                      threshold: float = 0.05) -> list[Finding]:
    """欠測メカニズム宣言と実装手法の決定的突合。

    `declared_mechanism`: "mcar"|"mar"|"mnar"（SAP 宣言）。
    `handling`: 実行 trace 由来の実装手法。
    `mnar_sensitivity`: MNAR 感度分析（delta 調整/pattern-mixture 等）を実施したか。
    `cc_covariate_only_justified`: 欠測が共変量のみで、条件付き MAR 下の
      complete-case が妥当と SAP で正当化されているか（White & Carlin 2010 の例外）。
    `max_missing_rate`: 解析変数群の最大欠測率（宣言欠如時の危険度判定に使う）。
    """
    mech = declared_mechanism.lower().strip() if declared_mechanism else None
    hand = handling.lower().strip() if handling else None

    # --- 完全未設定 ---
    if mech is None and hand is None:
        if max_missing_rate is not None and max_missing_rate > threshold:
            # 未宣言は危険側。check_l（未宣言の打ち切り＝FAIL）と同じ思想で
            # INCOMPLETE ではなく FAIL にする。
            return [Finding("E", Status.FAIL, Severity.MAJOR,
                f"最大欠測率{max_missing_rate:.1%}が閾値{threshold:.0%}超だが"
                "欠測メカニズムも処理手法も未宣言",
                f"declared_mechanism=None, handling=None, "
                f"max_missing_rate={max_missing_rate:.4f}",
                rule_id=_RULE, taxonomy_id="E")]
        return []

    # --- half-configured（片側のみ宣言）→ 監査不能 ---
    if mech is None or hand is None:
        return [Finding("E", Status.INCOMPLETE, Severity.CRITICAL,
            "欠測メカニズム監査の設定が不完全（メカニズム宣言と実装手法の一方のみ）で監査不能",
            f"declared_mechanism={declared_mechanism!r}, handling={handling!r}",
            rule_id=_RULE, taxonomy_id="E")]

    if mech not in _MECHANISMS:
        return [Finding("E", Status.INCOMPLETE, Severity.CRITICAL,
            f"未知の欠測メカニズム宣言で照合不能: {declared_mechanism!r}",
            f"許容値={sorted(_MECHANISMS)}", rule_id=_RULE, taxonomy_id="E")]
    if hand not in _HANDLINGS and hand not in _MNAR_OK_HANDLINGS:
        return [Finding("E", Status.INCOMPLETE, Severity.CRITICAL,
            f"未知の欠測処理手法で照合不能: {handling!r}",
            f"許容値={sorted(_HANDLINGS | _MNAR_OK_HANDLINGS)}",
            rule_id=_RULE, taxonomy_id="E")]

    ctx = f"declared_mechanism={mech}, handling={hand}"

    # --- 無処理（宣言はあるが handling=none）---
    if hand == "none":
        if max_missing_rate is not None and max_missing_rate > threshold:
            return [Finding("E", Status.FAIL, Severity.CRITICAL,
                f"欠測率{max_missing_rate:.1%}が閾値{threshold:.0%}超だが欠測処理なし",
                f"{ctx}, max_missing_rate={max_missing_rate:.4f}",
                rule_id=_RULE, taxonomy_id="E")]
        return [Finding("E", Status.PASS, Severity.MAJOR,
            "欠測が閾値以下で処理なしは許容", f"{ctx}, threshold={threshold}",
            rule_id=_RULE, taxonomy_id="E")]

    # --- missing-indicator 法 ---
    # 大規模疫学調査で広く使われる実務的手法だが、交絡調整の文脈では MCAR 下でも
    # バイアスを生じうることが知られる（Greenland & Finkle 1995, Am J Epidemiol
    # 142:1255）。「処理なし」ではないので CRITICAL にはしないが、妥当性は
    # Tier2/人間の判断に送る。
    if hand == "missing_indicator":
        return [Finding("E", Status.PASS, Severity.MAJOR,
            "欠測は missing-indicator 法で保持（妥当性は Tier2/人間が判定）",
            f"{ctx}。missing-indicator は交絡調整の文脈では MCAR 下でもバイアスを"
            "生じうる（Greenland & Finkle 1995）。complete-case / MI との感度比較の"
            "有無を Tier2 が精査する",
            rule_id=_RULE, taxonomy_id="E")]

    # --- 単一代入は宣言メカニズムによらず分散過小評価 ---
    if hand == "single_imputation":
        return [Finding("E", Status.FAIL, Severity.MAJOR,
            "単一代入は分散を過小評価する（多重代入または尤度法へ）",
            f"{ctx}（Sterne et al 2009, BMJ 338:b2393）",
            rule_id=_RULE, taxonomy_id="E")]

    # --- MNAR 宣言には感度分析が要る ---
    if mech == "mnar":
        if mnar_sensitivity or hand in _MNAR_OK_HANDLINGS:
            return [Finding("E", Status.PASS, Severity.MAJOR,
                "MNAR 宣言に対し感度分析/MNAR 対応手法が宣言されている",
                f"{ctx}, mnar_sensitivity={mnar_sensitivity}",
                rule_id=_RULE, taxonomy_id="E")]
        return [Finding("E", Status.FAIL, Severity.MAJOR,
            "MNAR を宣言しながら MNAR 感度分析（delta 調整/pattern-mixture 等）がない",
            f"{ctx}, mnar_sensitivity=False。標準的な MI/complete-case は MAR 仮定に依存する",
            rule_id=_RULE, taxonomy_id="E")]

    # --- complete-case の欠測率が閾値以下なら良性（メカニズムによらず）---
    if hand == "complete_case" and max_missing_rate is not None \
            and max_missing_rate <= threshold:
        return [Finding("E", Status.PASS, Severity.MAJOR,
            f"complete-case だが欠測率{max_missing_rate:.2%}が閾値{threshold:.0%}以下で実害は小さい",
            f"{ctx}, max_missing_rate={max_missing_rate:.4f}",
            rule_id=_RULE, taxonomy_id="E")]

    # --- MAR × complete-case（無条件 FAIL にしない）---
    if mech == "mar" and hand == "complete_case":
        if cc_covariate_only_justified:
            return [Finding("E", Status.PASS, Severity.MAJOR,
                "MAR×complete-case だが共変量限定欠測として SAP で正当化済み"
                "（Tier2 で正当化の妥当性を精査）",
                f"{ctx}, cc_covariate_only_justified=True"
                "（White & Carlin 2010: 共変量条件付き MAR 下の CC は妥当でありうる）",
                rule_id=_RULE, taxonomy_id="E")]
        return [Finding("E", Status.FAIL, Severity.MAJOR,
            "MAR を宣言しながら complete-case 解析（正当化の宣言なし）",
            f"{ctx}, cc_covariate_only_justified=False。"
            "MI/IPW/FIML への変更、または共変量限定欠測の正当化宣言が要る",
            rule_id=_RULE, taxonomy_id="E")]

    # --- MCAR × complete-case は整合 ---
    if mech == "mcar" and hand == "complete_case":
        return [Finding("E", Status.PASS, Severity.MAJOR,
            "MCAR 宣言と complete-case は整合（ただし MCAR 仮定の真偽は検証不能）",
            f"{ctx}。宣言の真偽は Tier2/G0 の管轄であり本チェックの保証範囲外",
            rule_id=_RULE, taxonomy_id="E")]

    # --- 残り（MAR/MCAR × MI/IPW/FIML）は整合 ---
    return [Finding("E", Status.PASS, Severity.MAJOR,
        "宣言メカニズムと実装手法は整合",
        f"{ctx}。ただし imputation model の変数集合の妥当性は本チェックの保証範囲外"
        "（Tier2/G0）",
        rule_id=_RULE, taxonomy_id="E")]
