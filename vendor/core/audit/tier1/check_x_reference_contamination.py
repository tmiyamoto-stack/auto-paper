"""Check X（参照群/対照群の汚染＝比較の分母に曝露済みが混入していないか）。

## なぜ必要か

check B（フィルタ/除外手続きの集合突合）と check R（回帰変数/固定効果の集合突合）は
いずれも「コードが宣言どおりの手続きを適用したか」を見る。しかしどちらも、比較の
**参照側（reference/control/pre-period）の中身が本当に非曝露で構成されているか**は
照合しない。コードが「正しく」フィルタを適用しても、そのフィルタ集合が estimand に対して
誤っていれば、非曝露参照に曝露済み観測が紛れ込む。これは2つの実論文で独立に発生した:

- **経済ショック論文の event study**: onset を「任意の 0→1 遷移の最小年」と定義したため、
  初回観測波で既に減収を報告していた個人が後年の 0→1 で onset を得て、その曝露済み初回波が
  pre-trend ビン(k≤−2)へ落ちた。**k≤−2 の人年の 30.7%(1,396/4,545)が実際には曝露(income_loss=1)**、
  参照カテゴリ(k=−1)の 20.6% も曝露済みだった。pre-trend 検定と平行トレンドの主張が汚染された。
- **加熱式タバコ論文の頻度解析**: 二値の「非使用」参照(7,908 person-wave)に対し、頻度解析の
  「0日(非使用)」参照は 8,180 で、差の **272 person-wave が「現在使用者だが過去30日0日回答」**。

## 何を決定的に照合するか

上流（工程3）が、比較の参照側に相当する各群について次を供給する:
`{id, exposure_var, exposed_in_reference, reference_total, tolerance?, label?, evidence?}`。
`exposed_in_reference / reference_total` が `tolerance`（既定 0.0）を超えれば FAIL。

## 独立性の限界（正直な開示・Fable 指摘 C-2）

本チェックは上流が申告した `exposed_in_reference` という**数値そのもの**を検証する。その数を
どの曝露指標から数えたかは契約の外にあるため、欠陥を作った当の工程3が自分の（誤った）派生
定義で数えれば 0 を申告でき、原理的には汚染設計に PASS を刻める。この循環を完全には断てない
が、緩和として **`exposure_var`（派生前の生曝露列名）の宣言を必須**にし、`exposed_in_reference`
は「参照メンバー集合 ∧ 生曝露列==曝露」で数えたものであることを契約で要求する（`exposure_var`
欠落は INCOMPLETE）。理想は共有 pipeline ヘルパで参照集合×生列を join して本チェック側で
再計算し、manifest hash で束ねることであり、それは今後の hardening 課題として残す。ここが
保証するのは「宣言された参照の中身が、宣言どおり非曝露で構成されているか」だけである。
「参照の定義自体が妥当か」は SAP（G0）と Tier2/3 の識別戦略判断に属する。

## tolerance は消音ノブになりうる（M-1）

`tolerance` は上流（＝摘発対象と同じ供給者）が握るため、大きな値で汚染を黙らせられる。
上限 0.05 を超える tolerance は INCOMPLETE とし、0 を超える tolerance を使った群は
その旨を evidence に明示して surface する（人間・Tier2/3 が正当性を判断できるように）。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity

_RULE = "t1.contamination.reference_group"
_TAX = "I"
_REQUIRED_FIELDS = ("id", "exposure_var", "exposed_in_reference", "reference_total")
_TOLERANCE_CAP = 0.05


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_x_reference_contamination(reference_groups: list[dict] | None) -> list[Finding]:
    if not reference_groups:
        return [
            Finding("X", Status.INCOMPLETE, Severity.CRITICAL,
                    "参照/対照群の構成が供給されず汚染判定不能",
                    "reference_groups=[]",
                    rule_id=_RULE, taxonomy_id=_TAX)
        ]

    findings: list[Finding] = []
    for g in reference_groups:
        gid = g.get("id", "<no-id>")
        label = g.get("label", gid)

        missing = [k for k in _REQUIRED_FIELDS if g.get(k) in (None, "")]
        if missing:
            findings.append(
                Finding("X", Status.INCOMPLETE, Severity.CRITICAL,
                        f"参照群の必須フィールド欠落: {gid}",
                        f"欠落 {sorted(missing)}（exposure_var=派生前の生曝露列名を必須化＝自己申告循環の緩和）",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))
            continue

        total = g["reference_total"]
        exposed = g["exposed_in_reference"]
        tol = g.get("tolerance", 0.0)

        if not (_num(total) and _num(exposed) and _num(tol)):
            findings.append(
                Finding("X", Status.INCOMPLETE, Severity.CRITICAL,
                        f"参照群の数値フィールドが非数値: {gid}",
                        f"reference_total={total!r} exposed={exposed!r} tolerance={tol!r}",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))
            continue
        if total <= 0:
            findings.append(
                Finding("X", Status.INCOMPLETE, Severity.CRITICAL,
                        f"参照群の総数が0以下で割合算出不能: {gid}",
                        f"reference_total={total}",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))
            continue
        if not (0 <= exposed <= total):
            findings.append(
                Finding("X", Status.INCOMPLETE, Severity.CRITICAL,
                        f"参照群の曝露数が範囲外（計数バグの疑い）: {gid}",
                        f"exposed={exposed} は [0, {total}] の外",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))
            continue
        if not (0 <= tol <= _TOLERANCE_CAP):
            findings.append(
                Finding("X", Status.INCOMPLETE, Severity.CRITICAL,
                        f"tolerance が許容上限 {_TOLERANCE_CAP:.0%} を超過（消音ノブの疑い）: {gid}",
                        f"tolerance={tol}（SAP 由来の正当化と上限内の値を要求）",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))
            continue

        frac = exposed / total
        tol_note = f" | 非ゼロ許容 tolerance={tol:.1%} を使用（要正当化）" if tol > 0 else ""
        if frac > tol:
            findings.append(
                Finding("X", Status.FAIL, Severity.CRITICAL,
                        f"参照/pre-period 群に曝露済み観測が混入: {label}",
                        f"exposed={exposed}/{total} ({frac:.1%}) > 許容 {tol:.1%} "
                        f"[exposure_var={g['exposure_var']}] | {g.get('evidence', '')}",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))
        else:
            findings.append(
                Finding("X", Status.PASS, Severity.CRITICAL,
                        f"参照/pre-period 群は非曝露で構成: {label}",
                        f"exposed={exposed}/{total} ({frac:.1%}) ≤ 許容 {tol:.1%} "
                        f"[exposure_var={g['exposure_var']}]{tol_note}",
                        variable=gid, rule_id=_RULE, taxonomy_id=_TAX))

    return findings
