"""Check H（パネル脱落の差分＝標準化差の再計算とサーフェシング）。

共同研究者レビュー指摘2-(3)。`rule_id="t1.attrition.differential"`、check_id "H"、
taxonomy H（選択バイアス・パネル構造）。

## 決定的なのは「再計算」だけ（両レビューの一致点）

決定的にできるのは、残存者 vs 脱落者の baseline 標準化差（SMD）と群別残存率の**再計算**
である。「脱落が選択的で推論を歪めた」は決定的ではない——特に MNAR 脱落（将来の未観測
アウトカムに依存する脱落）は baseline 比較が全て非有意でもすり抜ける。したがって本規則の
mode は **surfacing / MAJOR（非ブロック）**とし、FAIL が意味するのは
「**差分脱落があるのに開示も対処もされていない**」という報告欠陥に限定する。

## p 値を使わない理由（Codex Sol の反例）

baseline 差の p 値で選択性を確定すると、大標本で平均年齢差 0.3 歳が p<0.001 となり
**正しい原稿を FAIL** させる。標本サイズに依存しない標準化差（SMD）を使う。

## 閾値と偽陽性抑制

- SAP 宣言の主要変数（曝露・アウトカム baseline・主要交絡）は |SMD| > **0.10**
  （Normand et al 2001 / Austin & Stuart 2015 のバランス診断慣行）。
- それ以外の baseline 変数は |SMD| > **0.25** のみ（Rubin 2001）。20変数に 0.10 を
  一律適用すると偶然の超過で precision ≥ 80% を割るため、意図的に緩める。
- 群 n < 30 の変数は SMD がノイズで暴れるため 0.25 規則のみ適用。
- 横断研究（`is_panel` が False/None かつ入力なし）は完全に対象外（finding ゼロ）。
"""
from __future__ import annotations

import math

from .findings import Finding, Status, Severity

_RULE = "t1.attrition.differential"

_SMD_KEY = 0.10
_SMD_OTHER = 0.25
_MIN_GROUP_N = 30
# 曝露群間の残存率差（パーセントポイント）。WWC attrition standards の保守側境界。
_RETENTION_GAP_PP = 0.05


def _mean(xs) -> float:
    return sum(xs) / len(xs)


def _var(xs) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def standardized_mean_difference(a, b) -> float | None:
    """プールSDで標準化した平均差。決定的な算術（標本サイズ非依存）。

    二値変数（0/1のみ）は p(1-p) 版のプール分散を使う。プール分散0（両群定数かつ
    同値）は差なしとして 0.0、両群定数だが値が違う場合は判定不能で None。
    """
    if not a or not b:
        return None
    va, vb = _var(a), _var(b)
    binary = set(a) | set(b) <= {0, 1, 0.0, 1.0}
    if binary:
        pa, pb = _mean(a), _mean(b)
        pooled = (pa * (1 - pa) + pb * (1 - pb)) / 2
    else:
        pooled = (va + vb) / 2
    diff = _mean(a) - _mean(b)
    if pooled <= 0:
        return 0.0 if diff == 0 else None
    return diff / math.sqrt(pooled)


def check_h_attrition(baseline_by_var: dict[str, dict[str, list[float]]] | None,
                      key_vars: set[str] | None = None,
                      handled_declared: bool = False,
                      retention_by_group: dict[str, float] | None = None,
                      is_panel: bool | None = None,
                      smd_key_threshold: float = _SMD_KEY,
                      smd_other_threshold: float = _SMD_OTHER,
                      min_group_n: int = _MIN_GROUP_N) -> list[Finding]:
    """残存者 vs 脱落者の baseline 差分を再計算し、未開示の差分脱落を surface する。

    `baseline_by_var`: {変数: {"completers": [...], "dropouts": [...]}}。
    `key_vars`: SAP 宣言の主要変数（厳しい閾値を適用する集合）。
    `handled_declared`: 差分脱落表の報告 or IPW/重み補正等の対処が宣言されているか。
    `retention_by_group`: {曝露群: 残存率}。
    `is_panel`: SAP がパネル/縦断デザインを宣言しているか。
    """
    if baseline_by_var is None:
        if is_panel:
            # パネル論文で脱落監査の材料が無いのはカバレッジの穴（fail-closed）。
            return [Finding("H", Status.INCOMPLETE, Severity.MAJOR,
                "パネルデザイン宣言だが脱落 baseline 比較の材料未提供で監査不能",
                "is_panel=True, attrition_baseline=None",
                rule_id=_RULE, taxonomy_id="H")]
        return []

    key_vars = key_vars or set()
    findings: list[Finding] = []
    imbalanced: list[str] = []

    for var in sorted(baseline_by_var):
        groups = baseline_by_var[var]
        comp = groups.get("completers") or []
        drop = groups.get("dropouts") or []
        if not comp or not drop:
            findings.append(Finding("H", Status.INCOMPLETE, Severity.MAJOR,
                f"残存者/脱落者の一方が空で標準化差を計算不能: {var}",
                f"n_completers={len(comp)}, n_dropouts={len(drop)}",
                variable=var, rule_id=_RULE, taxonomy_id="H"))
            continue

        smd = standardized_mean_difference(comp, drop)
        if smd is None:
            findings.append(Finding("H", Status.INCOMPLETE, Severity.MAJOR,
                f"分散0かつ群間で値が異なり標準化差を定義不能: {var}",
                f"n_completers={len(comp)}, n_dropouts={len(drop)}",
                variable=var, rule_id=_RULE, taxonomy_id="H"))
            continue

        small = min(len(comp), len(drop)) < min_group_n
        if var in key_vars and not small:
            threshold, label = smd_key_threshold, "主要変数"
        else:
            threshold, label = smd_other_threshold, (
                "小群(n<%d)" % min_group_n if small else "非主要変数")

        if abs(smd) > threshold:
            imbalanced.append(f"{var}(SMD={smd:+.3f})")
            # 変数ごとの超過は**材料の提示**であって欠陥の確定ではない。FAIL にするのは
            # 「差分脱落があるのに開示も対処もされていない」という報告欠陥（下の集約
            # finding）だけ。ここで FAIL を出すと、差分脱落を正しく開示・補正した原稿
            # （handled_declared=True）にも FAIL が残り、偽陽性になる。
            findings.append(Finding("H", Status.PASS, Severity.MAJOR,
                f"残存者と脱落者の baseline 差が閾値超: {var}（材料提示）",
                f"SMD={smd:+.4f}, |SMD|>{threshold}({label}), "
                f"n_completers={len(comp)}, n_dropouts={len(drop)}。"
                "※差分脱落の存在自体は欠陥ではない。開示と対処の有無は集約 finding で判定",
                variable=var, rule_id=_RULE, taxonomy_id="H"))
        else:
            findings.append(Finding("H", Status.PASS, Severity.MAJOR,
                f"残存者と脱落者の baseline 差は閾値以内: {var}",
                f"SMD={smd:+.4f}, 閾値={threshold}({label})",
                variable=var, rule_id=_RULE, taxonomy_id="H"))

    if retention_by_group:
        rates = retention_by_group
        gap = max(rates.values()) - min(rates.values())
        if gap > _RETENTION_GAP_PP:
            imbalanced.append(f"群間残存率差={gap:.1%}")
            # 変数側と同じく材料提示に留める（FAIL の本体は集約 finding）。
            findings.append(Finding("H", Status.PASS, Severity.MAJOR,
                "曝露群間の残存率差が閾値超（材料提示）",
                f"残存率={ {k: round(v, 4) for k, v in sorted(rates.items())} }, "
                f"差={gap:.4f} > {_RETENTION_GAP_PP}",
                rule_id=_RULE, taxonomy_id="H"))

    # 差分が見つかったのに開示も対処もされていない＝報告欠陥（ここが FAIL の本体）。
    if imbalanced and not handled_declared:
        findings.append(Finding("H", Status.FAIL, Severity.MAJOR,
            "差分脱落が検出されたが差分脱落表の報告も補正の宣言もない",
            f"不均衡項目={sorted(imbalanced)}, handled_declared=False。"
            "差分脱落表の提示、または IPW/重み補正の宣言が要る。"
            "※MNAR 脱落は baseline 比較ですり抜けるため、本チェックの PASS は"
            "「選択的でない」ことの証明ではない",
            rule_id=_RULE, taxonomy_id="H"))
    elif imbalanced:
        findings.append(Finding("H", Status.PASS, Severity.MAJOR,
            "差分脱落は検出されたが開示/補正が宣言されている（誠実さは Tier2 が判定）",
            f"不均衡項目={sorted(imbalanced)}, handled_declared=True",
            rule_id=_RULE, taxonomy_id="H"))

    return findings
