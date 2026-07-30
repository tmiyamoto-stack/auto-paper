"""Check W（IPW 重みの健全性と有効サンプルサイズ）。

共同研究者レビュー指摘2-(1)。ただし **Fable と Codex Sol の両レビューが一致して
警告した通り、「重み分布が悪い＝推論が不健全」は決定的に判定できない**。本モジュールは
それを2つの規則に分割し、mode を分けて実装する。

- `t1.weights.arithmetic`（**決定的** / CRITICAL）: 算術と宣言↔実装の突合のみ。
  非有限値・負値・全ゼロ、`stabilized` 宣言下の平均乖離、`trimmed` 宣言下の上限超過、
  対象者数と重みベクトル長の不一致。いずれも「計算すれば真偽が決まる」ものだけ。
- `t1.weights.distribution`（**サーフェシング** / MAJOR・非ブロック）: ESS 比・最大重み。
  ここは判定でなく材料提供に留める。

## なぜ普遍閾値でハード FAIL にしないか（Codex Sol の反例）

稀な曝露を扱う**正しい**解析で max weight=40 / ESS比=45% は普通に起きる。これを FAIL に
すると正しい原稿を落とす。逆に重みを 10 で不適切にクリップした欠陥解析は max≤10 で
PASS してしまい、estimand の変更と positivity 違反を隠す。したがって:

- ESS 比・最大重みは **SAP で事前宣言された閾値があればそれを使う**（宣言値の超過は
  「宣言に反した」という決定的事実）。宣言が無ければ既定値で surface するのみで、
  finding 文面に「Tier2/人間が判定する材料であり欠陥の確定ではない」と明記する。
- 調査ウェイト（sampling/raking weights）と frequency weights は `kind` 宣言で
  mean≈1 規則から除外する（正当に広い分布を持つため）。

## 決定的と称してよい範囲（SKILL.md §0 と整合）

決定的なのは (a) ESS 等の算術再計算、(b) 宣言と実装の文字通りの矛盾、の2つだけである。
「positivity が満たされているか」「重み付けが妥当か」は本チェックの管轄外（Tier2/G0）。
"""
from __future__ import annotations

import math

from .findings import Finding, Status, Severity

_RULE_ARITH = "t1.weights.arithmetic"
_RULE_DIST = "t1.weights.distribution"

# 安定化重みの平均は ≈1 であるべき（Cole & Hernán 2008, Am J Epidemiol 168:656）。
# 乖離は PS モデル誤指定か positivity 違反のシグナル。
_STAB_MEAN_TOL = 0.10
# ESS/N の surfacing 既定。正典的根拠のある値ではなく「情報量が半減する点」という
# 実務上の目安。SAP 宣言があればそちらを優先する。
_ESS_RATIO_MIN = 0.50
# trimming 未宣言時に surface する安定化重みの上限（truncation 感度分析の慣行的目安）。
_UNTRIMMED_MAX = 10.0

# mean≈1 規則を適用しない重み種別（正当に広い分布を持つ）。
_MEAN_EXEMPT_KINDS = {"sampling", "raking", "survey", "frequency"}


def _finite(values) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def effective_sample_size(weights) -> float:
    """Kish (1965) の ESS = (Σw)² / Σw²。純粋な算術（決定的）。"""
    s1 = sum(weights)
    s2 = sum(w * w for w in weights)
    if s2 == 0:
        return 0.0
    return (s1 * s1) / s2


def check_w_weights(weights_by_analysis: dict[str, list[float]] | None,
                    specs_by_analysis: dict[str, dict] | None = None,
                    weighting_declared: bool | None = None,
                    ess_ratio_min: float = _ESS_RATIO_MIN,
                    stab_mean_tol: float = _STAB_MEAN_TOL,
                    untrimmed_max: float = _UNTRIMMED_MAX) -> list[Finding]:
    """IPW 重みの決定的照合＋分布サーフェシング。

    `weights_by_analysis`: {analysis_id: [w, ...]}（行レベルの最終重み）。
    `specs_by_analysis`: {analysis_id: {"stabilized": bool, "trimmed": bool,
      "trim_bound": [lo, hi], "kind": str, "n_subjects": int,
      "ess_ratio_min": float}}。SAP 由来の宣言。
    `weighting_declared`: SAP が重み付け解析を宣言しているか。
    """
    findings: list[Finding] = []

    if weights_by_analysis is None:
        if weighting_declared:
            # 宣言があるのに重みが供給されない＝監査不能（fail-closed、サイレント PASS 禁止）。
            return [Finding("W", Status.INCOMPLETE, Severity.CRITICAL,
                "重み付け解析が宣言されているが重みベクトル未提供で監査不能",
                "weighting_declared=True, ipw_weights=None",
                rule_id=_RULE_ARITH, taxonomy_id="L")]
        return []

    specs_by_analysis = specs_by_analysis or {}

    for aid in sorted(weights_by_analysis):
        weights = weights_by_analysis[aid]
        spec = specs_by_analysis.get(aid, {})
        kind = str(spec.get("kind", "ipw")).lower()

        # --- 決定的: 算術健全性 ---
        if not weights:
            findings.append(Finding("W", Status.INCOMPLETE, Severity.CRITICAL,
                f"重みベクトルが空で監査不能: {aid}", f"analysis={aid}, n_weights=0",
                variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))
            continue

        if not _finite(weights):
            findings.append(Finding("W", Status.FAIL, Severity.CRITICAL,
                f"重みに非有限値(NaN/inf)または非数値: {aid}",
                f"analysis={aid}, n_weights={len(weights)}",
                variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))
            continue

        neg = [w for w in weights if w < 0]
        if neg:
            findings.append(Finding("W", Status.FAIL, Severity.CRITICAL,
                f"負の重みが存在: {aid}",
                f"analysis={aid}, 負値数={len(neg)}, min={min(weights)}",
                variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))
        if all(w == 0 for w in weights):
            findings.append(Finding("W", Status.FAIL, Severity.CRITICAL,
                f"全ての重みが0: {aid}", f"analysis={aid}, n_weights={len(weights)}",
                variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))
            continue

        n_declared = spec.get("n_subjects")
        if n_declared is not None and n_declared != len(weights):
            findings.append(Finding("W", Status.FAIL, Severity.CRITICAL,
                f"重みベクトル長が解析対象者数と不一致: {aid}",
                f"analysis={aid}, n_subjects宣言={n_declared}, n_weights={len(weights)}",
                variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))

        mean_w = sum(weights) / len(weights)
        max_w = max(weights)

        # 安定化宣言 → 平均≈1（宣言↔実装の決定的突合）。survey/frequency は除外。
        if spec.get("stabilized") and kind not in _MEAN_EXEMPT_KINDS:
            if abs(mean_w - 1.0) > stab_mean_tol:
                findings.append(Finding("W", Status.FAIL, Severity.CRITICAL,
                    f"安定化重みと宣言されているが平均が1から乖離: {aid}",
                    f"analysis={aid}, mean={mean_w:.4f}, 許容=1±{stab_mean_tol}"
                    "（Cole & Hernán 2008: 安定化重みの平均は≈1。乖離は PS モデル誤指定/"
                    "positivity 違反のシグナル）",
                    variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))

        # trimming 宣言 → 宣言上限の超過は決定的な宣言↔実装乖離。
        bound = spec.get("trim_bound")
        if spec.get("trimmed") and bound is not None:
            hi = bound[1] if isinstance(bound, (list, tuple)) else bound
            if hi is not None and max_w > hi:
                findings.append(Finding("W", Status.FAIL, Severity.CRITICAL,
                    f"trimming 宣言の上限を超える重みが残存: {aid}",
                    f"analysis={aid}, max={max_w:.4f}, 宣言上限={hi}",
                    variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))
        elif spec.get("trimmed") and bound is None:
            findings.append(Finding("W", Status.INCOMPLETE, Severity.CRITICAL,
                f"trimming 宣言があるが trim_bound 未宣言で照合不能: {aid}",
                f"analysis={aid}, trimmed=True, trim_bound=None",
                variable=aid, rule_id=_RULE_ARITH, taxonomy_id="L"))

        # --- サーフェシング: 分布特性（判定ではなく材料提供・非ブロック） ---
        if kind in _MEAN_EXEMPT_KINDS:
            continue

        n = n_declared if n_declared else len(weights)
        ess = effective_sample_size(weights)
        ratio = ess / n if n else 0.0
        declared_min = spec.get("ess_ratio_min")
        threshold = declared_min if declared_min is not None else ess_ratio_min
        source = "SAP宣言" if declared_min is not None else "既定"

        if ratio < threshold:
            findings.append(Finding("W", Status.FAIL, Severity.MAJOR,
                f"有効サンプルサイズ比が閾値未満: {aid}",
                f"analysis={aid}, ESS={ess:.1f}, N={n}, ESS/N={ratio:.3f} "
                f"< {threshold}({source})。"
                "※これは欠陥の確定ではない。稀な曝露の正しい解析でも低 ESS は生じる。"
                "Tier2/人間が positivity・estimand と併せて判定する材料である",
                variable=aid, rule_id=_RULE_DIST, taxonomy_id="H"))
        else:
            findings.append(Finding("W", Status.PASS, Severity.MAJOR,
                f"有効サンプルサイズ比は閾値以上: {aid}",
                f"analysis={aid}, ESS={ess:.1f}, N={n}, ESS/N={ratio:.3f} "
                f">= {threshold}({source})",
                variable=aid, rule_id=_RULE_DIST, taxonomy_id="H"))

        if not spec.get("trimmed") and spec.get("stabilized") and max_w > untrimmed_max:
            findings.append(Finding("W", Status.FAIL, Severity.MAJOR,
                f"trimming 未宣言で極端な安定化重みが残存: {aid}",
                f"analysis={aid}, max={max_w:.2f} > {untrimmed_max}（既定目安）。"
                "※truncation 感度分析の要否を Tier2/人間が判定する材料",
                variable=aid, rule_id=_RULE_DIST, taxonomy_id="H"))

    return findings
