"""Check Q（モデル診断＝収束と推定可能性の照合）。

共同研究者レビュー3 §4.2 の提案だが、**提案されたうち Hosmer–Lemeshow と QIC の
一律合否は実装しない**。Fable・Codex Sol の両レビューが一致して却下した。

## Hosmer–Lemeshow を決定的合否に使わない理由

HL 統計量の再計算自体は決定的だが、`p<0.05 → 不適合 → FAIL` という意味づけが不当。

- 検定力が標本サイズに依存し、N=11,533 では実質無視できる較正差でも有意になりやすい
- 群分け（通常10群）の取り方で結論が変わる
- 完全に正しいモデルでも設定した α の確率で棄却されるので、単独のハードゲートは
  原理的に偽陽性ゼロにならない
- そもそも関連・因果パラメータの推定を目的とする論文に、予測モデルとしての絶対較正を
  要求するのは目的不一致

**毎回鳴る警報は警報ではない**（precision を定義的に破壊する）。HL は値を evidence に
記録するだけで finding にしない。QIC も候補モデル間の相対基準であり絶対閾値を置かない。

## 何を決定的に照合するか

- **主要係数の推定可能性**: 原稿に掲載する係数が非推定・非有限、または共分散行列が
  定義不能 → CRITICAL。「Xで調整した」という記載が文字通り偽になるため。
- **宣言共変量 ↔ 実際に推定された項**: rank deficiency で共変量が黙って落ちた場合の検出。
  比較は**変数レベル**（参照カテゴリのダミー落ちを偽陽性にしない）。
- **収束・完全分離**: 原則 MAJOR サーフェシング。`converged=False` は反復上限や
  厳しすぎる tolerance に触れただけで、勾配が実質ゼロなら実害がないことがある
  （Codex Sol 指摘）。主要係数が実際に非推定の場合のみ CRITICAL へ昇格する。
- **SAP 宣言診断の実行**: 宣言した診断が実行されたかの存在照合（MAJOR）。
  QIC 選択を宣言した場合は argmin との突合（純算術）。
"""
from __future__ import annotations

import math

from .findings import Finding, Status, Severity

_RULE_EST = "t1.model.estimability"
_RULE_CONV = "t1.model.convergence"
_RULE_DIAG = "t1.model.diagnostics_declared"


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def check_q_model(model_trace: dict[str, dict] | None,
                  declared_terms: dict[str, list[str]] | None = None,
                  declared_diagnostics: dict[str, list[str]] | None = None,
                  regression_declared: bool | None = None) -> list[Finding]:
    """掲載モデルの収束・推定可能性・宣言診断を照合する。

    `model_trace`: {analysis_id: {
        "reported": bool,                 # 原稿に掲載するモデルか
        "converged": bool,
        "separation": bool,
        "estimated_vars": [str],          # 実際に係数が推定された変数（変数レベル）
        "dropped_vars": [str],
        "headline_coefs": {name: value},  # 掲載する主要係数
        "cov_defined": bool,
        "diagnostics_run": [str],
        "qic_by_structure": {str: float} | None,
        "chosen_structure": str | None}}
    `declared_terms`: {analysis_id: [宣言した共変量（変数レベル）]}
    `declared_diagnostics`: {analysis_id: [SAP宣言の診断名]}
    """
    if model_trace is None:
        if regression_declared:
            return [Finding("Q", Status.INCOMPLETE, Severity.CRITICAL,
                "回帰モデルが宣言されているがモデルtrace未提供で監査不能",
                "regression_declared=True, model_trace=None",
                rule_id=_RULE_EST, taxonomy_id="L")]
        return []

    declared_terms = declared_terms or {}
    declared_diagnostics = declared_diagnostics or {}
    findings: list[Finding] = []

    for aid in sorted(model_trace):
        tr = model_trace[aid]
        if not tr.get("reported", True):
            continue                       # 中間試行モデルは対象外

        # --- 主要係数の推定可能性（CRITICAL）---
        bad = [k for k, v in (tr.get("headline_coefs") or {}).items() if not _finite(v)]
        if bad:
            findings.append(Finding("Q", Status.FAIL, Severity.CRITICAL,
                f"掲載する主要係数が非推定または非有限: {aid}",
                f"analysis={aid}, 該当={sorted(bad)}",
                variable=aid, rule_id=_RULE_EST, taxonomy_id="L"))
        if tr.get("cov_defined") is False:
            findings.append(Finding("Q", Status.FAIL, Severity.CRITICAL,
                f"共分散行列が定義不能で標準誤差を報告できない: {aid}",
                f"analysis={aid}, cov_defined=False",
                variable=aid, rule_id=_RULE_EST, taxonomy_id="L"))

        # --- 宣言共変量 ↔ 推定された項（変数レベルで比較）---
        want = declared_terms.get(aid)
        if want is not None:
            est = set(tr.get("estimated_vars") or [])
            missing = sorted(set(want) - est)
            if missing:
                findings.append(Finding("Q", Status.FAIL, Severity.CRITICAL,
                    f"調整したと記載した共変量の係数が推定されていない: {aid}",
                    f"analysis={aid}, 未推定={missing}, "
                    f"dropped={sorted(tr.get('dropped_vars') or [])}"
                    "（rank deficiency 等で黙って落ちており、記載が文字通り偽になる）",
                    variable=aid, rule_id=_RULE_EST, taxonomy_id="L"))
            else:
                findings.append(Finding("Q", Status.PASS, Severity.CRITICAL,
                    f"宣言共変量はすべて推定されている: {aid}",
                    f"analysis={aid}, 変数数={len(want)}",
                    variable=aid, rule_id=_RULE_EST, taxonomy_id="L"))

        # --- 収束・完全分離（既定は MAJOR サーフェシング）---
        flags = []
        if tr.get("converged") is False:
            flags.append("収束フラグ False")
        if tr.get("separation"):
            flags.append("完全分離")
        if flags:
            findings.append(Finding("Q", Status.FAIL, Severity.MAJOR,
                f"収束・分離の警告が出ているモデルの推定値を掲載している: {aid}",
                f"analysis={aid}, {'/'.join(flags)}。"
                "※反復上限や厳しい tolerance に触れただけで実害がない場合がある。"
                "主要係数が実際に推定されていれば欠陥の確定ではなく、"
                "Tier2/人間が判定する材料",
                variable=aid, rule_id=_RULE_CONV, taxonomy_id="L"))

        # --- SAP 宣言診断の実行（存在照合）---
        want_diag = declared_diagnostics.get(aid)
        if want_diag:
            ran = set(tr.get("diagnostics_run") or [])
            not_run = sorted(set(want_diag) - ran)
            if not_run:
                findings.append(Finding("Q", Status.FAIL, Severity.MAJOR,
                    f"SAP宣言の診断が実行されていない: {aid}",
                    f"analysis={aid}, 未実行={not_run}",
                    variable=aid, rule_id=_RULE_DIAG, taxonomy_id="L"))

        # --- QIC 選択を宣言した場合の argmin 突合（純算術）---
        qic = tr.get("qic_by_structure")
        chosen = tr.get("chosen_structure")
        if qic and chosen is not None:
            best = min(qic, key=lambda k: qic[k])
            if chosen != best:
                findings.append(Finding("Q", Status.FAIL, Severity.MAJOR,
                    f"QIC最小でない相関構造が選択されている: {aid}",
                    f"analysis={aid}, 選択={chosen}(QIC={qic[chosen]}), "
                    f"最小={best}(QIC={qic[best]})",
                    variable=aid, rule_id=_RULE_DIAG, taxonomy_id="L"))

    return findings
