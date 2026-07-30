"""人間ゲート G1.5 の発火判定（数値ルールの確定実装）。

共同研究者レビュー指摘(3)。従来 SKILL.md/DESIGN.md には「点推定±20%／有意性の変化／
N の±5%」と書かれていただけで、**尺度・分母・丸め・境界が未定義**だったため運用が
安定しなかった。本モジュールがその定義を確定させる。

## G1.5 が判定するもの／しないもの

G1.5 は「自己修復の前後で**結論が動いたか**」を検出して人間に回すゲートであり、
「その変化が科学的に重要か」を判定するものではない。後者は人間（G1.5 レビュー本体）
の仕事である。よって発火は**保守的（迷ったら発火）**に倒す。

## 尺度別に定義する理由（Codex Sol の反例）

全尺度一律の「点推定±20%」は двух方向に壊れる:

- 比の尺度: OR 1.01→1.03 は生の OR では約2%の変化だが、log 効果量では約3倍になる。
  比の尺度は **log スケール**で比較しなければならない。
- 差の尺度: リスク差 0.001→0.0013 は相対30%変化だが臨床的にはほぼ無意味。旧推定値が
  0 近傍のとき相対変化率は発散するため、**SE 基準に切り替える**。

## 丸めと境界（Codex Sol 指摘）

- 比較は**未丸めの値**に対して行う。p=.049→.051 のような丸め由来の発火を避けるため、
  有意性の変化は p 値の文字列比較ではなく **CI が null を跨いだか**で判定する。
- 閾値境界は一貫して `>`（超過で発火、等号では発火しない）とする。

## fail-closed

旧値・新値のいずれかが欠落/パース不能なら、閾値に関係なく**発火**する（黙って通さない）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# 比の尺度（log スケールで比較する）。
RATIO_MEASURES = {"or", "rr", "hr", "irr", "pr", "ratio"}
# 差の尺度（絶対変化 or SE 基準で比較する）。
DIFF_MEASURES = {"md", "rd", "beta", "coef", "diff", "smd"}

DEFAULT_THRESHOLDS = {
    # ln(1.20)=0.1823。従来の「±20%」を log スケールで対称に定義したもの。
    "g15_log_ratio": math.log(1.20),
    # 差の尺度の相対変化閾値。
    "g15_diff_rel": 0.20,
    # 旧推定値が SE より小さい（ノイズに埋もれる）ときの代替閾値（SE 倍数）。
    "g15_diff_se_mult": 0.5,
    "g15_n_pct": 0.05,
    "alpha": 0.05,
}


@dataclass
class Estimate:
    """比較対象の推定値1件。未丸めの値を渡すこと。"""

    estimand_id: str
    measure: str                      # "or"/"hr"/"rd"/"beta" 等
    point: float | None
    se: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n: int | None = None
    primary: bool = True


@dataclass
class GateDecision:
    fired: bool
    reasons: list[str] = field(default_factory=list)


def _null_value(measure: str) -> float:
    return 1.0 if measure.lower() in RATIO_MEASURES else 0.0


def _crosses_null(est: Estimate) -> bool | None:
    """CI が null を含むか。判定不能なら None。"""
    if est.ci_low is None or est.ci_high is None:
        return None
    null = _null_value(est.measure)
    return est.ci_low <= null <= est.ci_high


def evaluate_g15(old: Estimate | None, new: Estimate | None,
                 thresholds: dict | None = None,
                 flow_old: dict | None = None,
                 flow_new: dict | None = None) -> GateDecision:
    """主要/副次アウトカム1件について G1.5 発火を判定する。

    副次アウトカム（`primary=False`）は**符号反転と推論状態の変化のみ**を見る。
    多アウトカム論文で副次に全規則を適用すると毎回発火し、ゲートが形骸化するため。
    """
    th = dict(DEFAULT_THRESHOLDS)
    th.update(thresholds or {})
    reasons: list[str] = []

    # --- fail-closed: 比較材料の欠落 ---
    if old is None or new is None:
        return GateDecision(True, ["比較対象の推定値が欠落（fail-closed で発火）"])
    if old.estimand_id != new.estimand_id:
        return GateDecision(True, [
            f"estimand が不一致（{old.estimand_id} vs {new.estimand_id}）。"
            "同一推定量を比較できないため発火"])
    if old.point is None or new.point is None:
        return GateDecision(True, [
            f"{old.estimand_id}: 点推定が取得不能（fail-closed で発火）"])

    measure = (old.measure or "").lower()
    null = _null_value(measure)
    primary = old.primary and new.primary

    # --- (1) 符号反転 / null 跨ぎ: 大きさ不問で必ず発火（主要・副次とも） ---
    if (old.point - null) * (new.point - null) < 0:
        reasons.append(
            f"{old.estimand_id}: 点推定が null({null}) を跨いで反転 "
            f"({old.point:.6g} → {new.point:.6g})")

    # --- (2) 推論状態の変化: CI が null を含むかの変化（主要・副次とも） ---
    old_cross, new_cross = _crosses_null(old), _crosses_null(new)
    if old_cross is None or new_cross is None:
        reasons.append(
            f"{old.estimand_id}: CI が取得不能で推論状態を比較できない（fail-closed で発火）")
    elif old_cross != new_cross:
        reasons.append(
            f"{old.estimand_id}: 推論状態が変化（CI が null を"
            f"{'含む→含まない' if old_cross else '含まない→含む'}、alpha={th['alpha']}）")

    if not primary:
        return GateDecision(bool(reasons), reasons)

    # --- (3) 効果量の変化: 尺度別 ---
    if measure in RATIO_MEASURES:
        if old.point <= 0 or new.point <= 0:
            reasons.append(
                f"{old.estimand_id}: 比の尺度に非正値（log 比較不能・fail-closed で発火）")
        else:
            delta = abs(math.log(new.point / old.point))
            if delta > th["g15_log_ratio"]:
                reasons.append(
                    f"{old.estimand_id}: 効果量が log スケールで閾値超に変化 "
                    f"(|Δln|={delta:.4f} > {th['g15_log_ratio']:.4f}, "
                    f"{old.point:.6g} → {new.point:.6g})")
    else:
        diff = abs(new.point - old.point)
        se = old.se
        # 旧推定値がノイズに埋もれる場合、相対変化率は発散するので SE 基準に切替。
        if se is not None and abs(old.point) < se:
            if diff > th["g15_diff_se_mult"] * se:
                reasons.append(
                    f"{old.estimand_id}: 推定値が SE 比で閾値超に変化 "
                    f"(|Δ|={diff:.6g} > {th['g15_diff_se_mult']}×SE={se:.6g}、"
                    "旧推定値が SE 未満のため SE 基準を適用)")
        elif old.point == 0:
            if diff > 0:
                reasons.append(
                    f"{old.estimand_id}: 旧推定値0からの変化（相対変化率が定義不能・発火）")
        else:
            rel = diff / abs(old.point)
            if rel > th["g15_diff_rel"]:
                reasons.append(
                    f"{old.estimand_id}: 効果量の相対変化が閾値超 "
                    f"({rel:.4f} > {th['g15_diff_rel']}, "
                    f"{old.point:.6g} → {new.point:.6g})")

    # --- (4) CI 脱出: 新点推定が旧 CI の外 ---
    if old.ci_low is not None and old.ci_high is not None:
        if not (old.ci_low <= new.point <= old.ci_high):
            reasons.append(
                f"{old.estimand_id}: 新点推定が旧CI[{old.ci_low:.6g}, "
                f"{old.ci_high:.6g}]の外に移動 ({new.point:.6g})")

    # --- (5) N の変化 ---
    if old.n is not None and new.n is not None and old.n > 0:
        rel_n = abs(new.n - old.n) / old.n
        if rel_n > th["g15_n_pct"]:
            reasons.append(
                f"{old.estimand_id}: 解析Nが閾値超に変化 "
                f"({rel_n:.4f} > {th['g15_n_pct']}, {old.n} → {new.n})")
    elif (old.n is None) != (new.n is None):
        reasons.append(f"{old.estimand_id}: N の一方が欠落（fail-closed で発火）")

    # --- (6) 除外フローの構造変化（N 合計が偶然一致しても結論に効く） ---
    reasons += _flow_reasons(flow_old, flow_new, th["g15_n_pct"])

    return GateDecision(bool(reasons), reasons)


def _flow_reasons(flow_old: dict | None, flow_new: dict | None,
                  n_pct: float) -> list[str]:
    if flow_old is None or flow_new is None:
        return []
    old_stages = {s["label"]: s["n"] for s in flow_old.get("stages", [])}
    new_stages = {s["label"]: s["n"] for s in flow_new.get("stages", [])}
    reasons: list[str] = []

    added = sorted(set(new_stages) - set(old_stages))
    removed = sorted(set(old_stages) - set(new_stages))
    if added:
        reasons.append(f"除外フローに段が追加: {added}")
    if removed:
        reasons.append(f"除外フローから段が削除: {removed}")
    for label in sorted(set(old_stages) & set(new_stages)):
        o, n = old_stages[label], new_stages[label]
        if o and abs(n - o) / o > n_pct:
            reasons.append(
                f"除外フロー段'{label}'のNが閾値超に変化 ({o} → {n})")
    return reasons


def evaluate_g15_all(pairs, thresholds: dict | None = None,
                     flow_old: dict | None = None,
                     flow_new: dict | None = None) -> GateDecision:
    """複数 estimand をまとめて判定（1件でも発火すれば G1.5 発火）。

    `pairs`: [(old: Estimate|None, new: Estimate|None), ...]
    """
    reasons: list[str] = []
    fired = False
    for old, new in pairs:
        d = evaluate_g15(old, new, thresholds, flow_old, flow_new)
        if d.fired:
            fired = True
        reasons += d.reasons
    return GateDecision(fired, reasons)
