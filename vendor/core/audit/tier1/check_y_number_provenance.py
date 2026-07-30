"""Check Y（原稿数値の由来照合＝掲載された数値が results に遡れるか）。

## なぜ必要か

SKILL.md §3 は「工程4のテンプレートは手書き数値を禁止し、全数値は results.json から
機械挿入されるため、転記ミスというエラークラス自体が構造的に消滅する」とする。だがこの
保証は**原稿がプレースホルダでレンダされている場合にのみ**成立する。原稿が手書き数値を
含むと、レンダの fail-closed（未解決プレースホルダの検出）を素通りし、数値監査が働かない。

これは実論文で発生した: 経済ショック論文（プレースホルダ化前の手書き原稿）では、本文の
交互作用検定 p 値を更新したのに **Table 4 脚注の p 値が旧値（女性 p=0.64／非正規 p=0.42）の
まま残存**した。正しい値は interaction_tests.json の 0.77／0.95 である。既存の数値照合は
「results 側に対応値が存在するか」の向きでしか見ておらず、**原稿側に results に無い数値が
紛れ込む**向きを見ていなかったため、この stale を捕捉できなかった。

## 何を決定的に照合するか

上流が (1) 原稿から抽出した掲載数値 `reported_numbers`
（`{location, value, decimals?, context?}`）と、(2) 権威ある計算出力の全数値
`results_values` を供給する。掲載数値それぞれについて、**その掲載桁で丸めた権威値が
一致するか**を判定し、存在しなければ CRITICAL FAIL。いずれかが未供給なら INCOMPLETE。

**既定は厳密（rel_tol=abs_tol=0）の丸め桁一致のみ。** これは意図的である（Fable 指摘 C-3）:
rel_tol を 1% など置くと、「是正後に主結論が僅かに動いた」旧値（本スキルの2論文でまさに
起きた事象）が近傍の権威値に誤マッチして stale を見逃す。掲載値の小数桁は不定になりうる
（float 化で "1.60"→1.6 と末尾ゼロが失われ丸め桁が緩む）ため、上流は可能なら `decimals`
（原文の小数桁）を供給する。供給されればそれを丸め桁に使う。

## 保証しないもの・偽陽性の主因は抽出契約にある（Fable 指摘 M-5）

`results_values` 自体の正しさ（工程3のコードと check B/R/X が負う）は保証しない。また
**平坦な数値集合との照合は衝突しうる**（stale 値が無関係な権威値と2桁一致すれば PASS＝
偽陰性）。恒久策は `results_values` を `{value, context}` 化し context も突合すること。
偽陽性の主因は算術ではなく**抽出仕様の不在**である: 引用年（"…2008"）、尺度アンカー
（"K6 0–24"）、"95% CI" の 95、正当な手計算派生値は results に無く FAIL しうる。したがって
上流（工程4/5）の抽出器は、こうした非結果数値を除外し、正当な派生値は `results_values`
に含めるか `context` で由来を明示する責務を負う。**なお派生値を results_values に足す行為は
上記の衝突偽陰性を増やす方向**に働くため、抽出の緩さと厳密さは同じノブで逆向きに緊張する。
"""
from __future__ import annotations

import math

from .findings import Finding, Status, Severity

_RULE = "t1.manuscript.number_provenance"
_TAX = "C"


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _ndigits(reported: float, decimals: int | None) -> int:
    if decimals is not None:
        return decimals
    s = repr(float(reported))
    if "e" in s or "E" in s:  # 科学記法は桁数を信頼できない→0桁（整数丸め）に倒す
        return 0
    return len(s.split(".")[1]) if "." in s else 0


def _matches(reported: float, auth: float, ndigits: int,
             rel_tol: float, abs_tol: float) -> bool:
    """権威値 auth が、掲載値 reported の丸め桁（既定）または明示許容内で一致するか。"""
    if round(auth, ndigits) == round(reported, ndigits):
        return True
    if rel_tol <= 0 and abs_tol <= 0:
        return False
    return abs(auth - reported) <= max(abs_tol, rel_tol * abs(auth))


def check_y_number_provenance(reported_numbers: list[dict] | None,
                              results_values: list[float] | None,
                              rel_tol: float = 0.0,
                              abs_tol: float = 0.0) -> list[Finding]:
    if reported_numbers is None or results_values is None:
        return [
            Finding("Y", Status.INCOMPLETE, Severity.CRITICAL,
                    "掲載数値または権威計算値が未供給で由来照合不能",
                    f"reported_numbers={'なし' if reported_numbers is None else len(reported_numbers)} "
                    f"results_values={'なし' if results_values is None else len(results_values)}",
                    rule_id=_RULE, taxonomy_id=_TAX)
        ]
    if not reported_numbers:
        return [
            Finding("Y", Status.INCOMPLETE, Severity.CRITICAL,
                    "原稿から抽出された掲載数値が空で由来照合不能",
                    "reported_numbers=[]",
                    rule_id=_RULE, taxonomy_id=_TAX)
        ]

    auth = [v for v in results_values if _num(v) and math.isfinite(v)]
    findings: list[Finding] = []
    for r in reported_numbers:
        val = r.get("value")
        loc = r.get("location", "<no-loc>")
        ctx = r.get("context", "")
        if not _num(val) or not math.isfinite(val):
            findings.append(
                Finding("Y", Status.INCOMPLETE, Severity.CRITICAL,
                        f"掲載数値がパース不能/非有限: {loc}",
                        f"value={val!r} ctx={ctx}",
                        variable=loc, rule_id=_RULE, taxonomy_id=_TAX))
            continue

        ndigits = _ndigits(val, r.get("decimals"))
        hits = sum(1 for a in auth if _matches(val, a, ndigits, rel_tol, abs_tol))
        if hits:
            note = "（複数の権威値と一致＝弱一致・衝突注意）" if hits > 1 else ""
            findings.append(
                Finding("Y", Status.PASS, Severity.CRITICAL,
                        f"掲載数値は権威計算値に一致: {loc}",
                        f"value={val} ctx={ctx} | 一致 {hits} 件{note}",
                        variable=loc, rule_id=_RULE, taxonomy_id=_TAX))
        else:
            findings.append(
                Finding("Y", Status.FAIL, Severity.CRITICAL,
                        f"掲載数値が results に遡れない（手書き転記/stale の疑い）: {loc}",
                        f"value={val} ctx={ctx} | 権威集合({len(auth)}件)に丸め桁一致なし",
                        variable=loc, rule_id=_RULE, taxonomy_id=_TAX))

    return findings
