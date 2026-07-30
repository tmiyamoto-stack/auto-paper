"""Check P（事前登録整合＝解析マニフェストの集合突合と多重性）。

共同研究者レビュー3 §4.2 の提案。ただし提案どおりの「自然言語 SAP と Python コードの
diff」としては**実装しない**。Fable・Codex Sol の両レビューが一致して、それは意味の
対応づけを要する Tier2 判断であり、決定的チェックに偽装してはならないとした。

## 何を突合するか

check B（`methods_claims.json` ↔ `code_filters.json`）と同型で、**2つの機械可読
マニフェストの集合比較**にする。

- `sap_analyses`: G0（設計ゲート）通過時に凍結された解析マニフェスト
- `executed_analyses`: 工程3が実行時に吐く trace（静的なコード解析ではない）

比較は `analysis_id` と正規化フィールドの集合差、および補正 p 値の**再計算**のみ。
どちらも §10 の「算術の再計算」「宣言と実装の文字通りの突合」に収まる。

## ハッシュ凍結が本質（Fable 指摘）

事前登録の主張は本質的に**時間軸の主張**（「解析の *前に* 決めた」）である。
マニフェストを事後編集できるなら、集合突合が完全に通ったうえで prereg として
無意味になる。したがって G0 承認時の SAP 原文ハッシュを照合し、
**未供給なら INCOMPLETE で fail-closed**とする。

## 偽陽性を避ける設計（Codex Sol 指摘）

- SAP に無い解析でも `role="exploratory"` かつ原稿で探索的と明示されていれば
  **MAJOR surfacing** に留める。探索的解析を confirmatory family に自動編入しない。
- CRITICAL にするのは、**confirmatory family に未登録の解析が primary として
  追加された**ことが完全一致で示された場合だけ。
- 記述統計（検定を伴わない Table 1 等）は「解析」に数えない。
- SAP 改訂は `amended=True` と改訂ハッシュがあれば FAIL でなく surface。

## 保証しないもの

自然言語 SAP から `sap_analyses` への構造化が忠実かは**保証しない**（check B が
`methods_claims.json` に対して負っているのと同型の制約）。構造化の忠実性は G0 の
人間承認と Tier2 の抜き取り照合に委ねる。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity

_RULE_SET = "t1.prereg.analysis_set"
_RULE_MULT = "t1.prereg.multiplicity"


def _key(a: dict) -> tuple:
    """解析の同一性キー。粒度は outcome×exposure×contrast×model×集団。"""
    return (str(a.get("outcome", "")), str(a.get("exposure", "")),
            str(a.get("contrast", "")), str(a.get("model", "")),
            str(a.get("population", "")))


def _bh(pvals: list[float]) -> list[float]:
    """Benjamini–Hochberg 補正 p の再計算（純算術）。"""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    out = [0.0] * n
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        k = n - rank + 1
        prev = min(prev, pvals[i] * n / k)
        out[i] = min(prev, 1.0)
    return out


def check_p_prereg(sap_analyses: list[dict] | None,
                   executed_analyses: list[dict] | None,
                   sap_hash_expected: str | None = None,
                   sap_hash_actual: str | None = None,
                   adjusted_p_reported: dict[str, list[float]] | None = None,
                   preregistration_claimed: bool | None = None) -> list[Finding]:
    """事前登録マニフェストと実行 trace を突合する。

    `sap_analyses`: [{"analysis_id","role","family_id","outcome","exposure",
        "contrast","model","population","multiplicity":{"method","family"}}]
    `executed_analyses`: 同スキーマ ＋ {"reported_in_manuscript": bool,
        "labeled_exploratory": bool, "raw_p": [float]}
    `sap_hash_expected` / `sap_hash_actual`: G0 承認時と現在の SAP 原文 sha256。
    `adjusted_p_reported`: {family_id: [報告された補正p]}。
    `preregistration_claimed`: 原稿が事前登録を標榜しているか。
    """
    if sap_analyses is None and executed_analyses is None:
        if preregistration_claimed:
            return [Finding("P", Status.INCOMPLETE, Severity.CRITICAL,
                "事前登録を標榜しているが解析マニフェスト未提供で監査不能",
                "sap_analyses=None, executed_analyses=None",
                rule_id=_RULE_SET, taxonomy_id="B")]
        return []

    if sap_analyses is None or executed_analyses is None:
        return [Finding("P", Status.INCOMPLETE, Severity.CRITICAL,
            "事前登録監査の設定が不完全（SAP側・実行trace側の一方のみ）で監査不能",
            f"sap_analyses={'set' if sap_analyses is not None else 'None'}, "
            f"executed_analyses={'set' if executed_analyses is not None else 'None'}",
            rule_id=_RULE_SET, taxonomy_id="B")]

    findings: list[Finding] = []

    # --- SAP の凍結（事前登録の主張は時間軸の主張）------------------------------
    if sap_hash_expected is None or sap_hash_actual is None:
        findings.append(Finding("P", Status.INCOMPLETE, Severity.CRITICAL,
            "SAPのハッシュ凍結が未供給で、事前登録としての照合が成立しない",
            f"sap_hash_expected={sap_hash_expected}, sap_hash_actual={sap_hash_actual}。"
            "マニフェストを事後編集できる状態では集合突合が通っても prereg の意味を持たない",
            rule_id=_RULE_SET, taxonomy_id="B"))
    elif sap_hash_expected != sap_hash_actual:
        findings.append(Finding("P", Status.FAIL, Severity.CRITICAL,
            "G0承認時のSAPと現在のSAPのハッシュが不一致（事後改変の疑い）",
            f"G0承認時={sap_hash_expected[:16]}…, 現在={sap_hash_actual[:16]}…。"
            "SAP変更はG0を再通過する必要がある",
            rule_id=_RULE_SET, taxonomy_id="B"))
    else:
        findings.append(Finding("P", Status.PASS, Severity.CRITICAL,
            "SAPはG0承認時から改変されていない",
            f"sha256={sap_hash_actual[:16]}…", rule_id=_RULE_SET, taxonomy_id="B"))

    sap_by_key = {_key(a): a for a in sap_analyses}
    sap_ids = {a.get("analysis_id") for a in sap_analyses}

    # --- 方向1: 実行され報告された解析が SAP にあるか ---------------------------
    for ex in executed_analyses:
        if not ex.get("reported_in_manuscript"):
            continue                      # 中間試行は対象外
        aid = ex.get("analysis_id")
        registered = aid in sap_ids or _key(ex) in sap_by_key
        if registered:
            continue
        if ex.get("labeled_exploratory"):
            findings.append(Finding("P", Status.FAIL, Severity.MAJOR,
                f"SAP未登録の解析が報告されている（探索的と明示）: {aid or _key(ex)}",
                f"outcome={ex.get('outcome')}, exposure={ex.get('exposure')}。"
                "探索的ラベルがあるため MAJOR に留める。ラベルの誠実さは Tier2 が判定",
                variable=str(aid), rule_id=_RULE_SET, taxonomy_id="B"))
        elif str(ex.get("role", "")).lower() in ("primary", "confirmatory"):
            findings.append(Finding("P", Status.FAIL, Severity.CRITICAL,
                f"SAP未登録の解析がprimaryとして報告されている: {aid or _key(ex)}",
                f"outcome={ex.get('outcome')}, exposure={ex.get('exposure')}, "
                f"role={ex.get('role')}（無申告のpost-hoc主要解析）",
                variable=str(aid), rule_id=_RULE_SET, taxonomy_id="B"))
        else:
            findings.append(Finding("P", Status.FAIL, Severity.MAJOR,
                f"SAP未登録の解析が報告されている: {aid or _key(ex)}",
                f"outcome={ex.get('outcome')}, exposure={ex.get('exposure')}, "
                f"role={ex.get('role')}。探索的である旨の明示がない",
                variable=str(aid), rule_id=_RULE_SET, taxonomy_id="B"))

    # --- 方向2: SAP 宣言の解析が報告されているか（選択的非報告）-----------------
    reported_ids = {e.get("analysis_id") for e in executed_analyses
                    if e.get("reported_in_manuscript")}
    reported_keys = {_key(e) for e in executed_analyses if e.get("reported_in_manuscript")}
    for a in sap_analyses:
        aid = a.get("analysis_id")
        if aid in reported_ids or _key(a) in reported_keys:
            continue
        if a.get("amended"):
            findings.append(Finding("P", Status.PASS, Severity.MAJOR,
                f"SAP宣言の解析が未報告だが改訂記録がある: {aid}",
                f"amended=True。改訂の妥当性は G0/Tier2 が判定",
                variable=str(aid), rule_id=_RULE_SET, taxonomy_id="B"))
            continue
        sev = (Severity.CRITICAL if str(a.get("role", "")).lower() in ("primary", "confirmatory")
               else Severity.MAJOR)
        findings.append(Finding("P", Status.FAIL, sev,
            f"SAP宣言の解析が原稿に報告されていない: {aid}",
            f"role={a.get('role')}, outcome={a.get('outcome')}（選択的非報告の疑い）",
            variable=str(aid), rule_id=_RULE_SET, taxonomy_id="B"))

    # --- 多重性: 補正p の再計算（純算術）----------------------------------------
    findings += _check_multiplicity(sap_analyses, executed_analyses, adjusted_p_reported)
    return findings


def _check_multiplicity(sap_analyses, executed_analyses, adjusted_p_reported) -> list[Finding]:
    """SAP 宣言の補正法で補正 p を再計算し、報告値と突合する。

    「検定が多いのに補正が無い」という判定はしない（family の構成は学術判断であり、
    検定数の閾値でハード FAIL にすると正しい原稿を落とす）。検定数と family 構成は
    evidence に載せて Tier2 へ渡す。
    """
    out: list[Finding] = []
    fams: dict[str, dict] = {}
    for a in sap_analyses:
        fid = a.get("family_id")
        if fid and a.get("multiplicity"):
            fams[fid] = a["multiplicity"]
    if not fams:
        return out

    by_family: dict[str, list[float]] = {}
    for e in executed_analyses:
        fid = e.get("family_id")
        if fid in fams:
            by_family.setdefault(fid, []).extend(e.get("raw_p") or [])

    for fid, mult in sorted(fams.items()):
        raw = by_family.get(fid) or []
        method = str(mult.get("method", "")).lower()
        if not raw:
            out.append(Finding("P", Status.INCOMPLETE, Severity.MAJOR,
                f"多重性family の生p値が未供給で補正を再計算不能: {fid}",
                f"family={fid}, 宣言補正法={method or '未宣言'}",
                variable=fid, rule_id=_RULE_MULT, taxonomy_id="B"))
            continue

        if method in ("bonferroni", "bh", "fdr", "benjamini-hochberg"):
            if method == "bonferroni":
                recomputed = [min(p * len(raw), 1.0) for p in raw]
            else:
                recomputed = _bh(raw)
            reported = (adjusted_p_reported or {}).get(fid)
            if reported is None:
                out.append(Finding("P", Status.INCOMPLETE, Severity.MAJOR,
                    f"補正p の報告値が未供給で突合不能: {fid}",
                    f"family={fid}, 検定数={len(raw)}, 宣言補正法={method}",
                    variable=fid, rule_id=_RULE_MULT, taxonomy_id="B"))
            elif len(reported) != len(recomputed) or any(
                    abs(a - b) > 1e-6 for a, b in zip(sorted(reported), sorted(recomputed))):
                out.append(Finding("P", Status.FAIL, Severity.MAJOR,
                    f"報告された補正p が宣言補正法の再計算と一致しない: {fid}",
                    f"family={fid}, 方法={method}, 検定数={len(raw)}, "
                    f"報告={sorted(round(x, 6) for x in reported)}, "
                    f"再計算={sorted(round(x, 6) for x in recomputed)}",
                    variable=fid, rule_id=_RULE_MULT, taxonomy_id="B"))
            else:
                out.append(Finding("P", Status.PASS, Severity.MAJOR,
                    f"補正p は宣言補正法の再計算と一致: {fid}",
                    f"family={fid}, 方法={method}, 検定数={len(raw)}",
                    variable=fid, rule_id=_RULE_MULT, taxonomy_id="B"))
        else:
            out.append(Finding("P", Status.PASS, Severity.MAJOR,
                f"多重性の構成を報告（補正法は宣言なし/非対応、判定はTier2）: {fid}",
                f"family={fid}, 検定数={len(raw)}, 宣言補正法={method or '未宣言'}。"
                "※検定数だけを根拠に補正の要否を機械判定しない",
                variable=fid, rule_id=_RULE_MULT, taxonomy_id="B"))
    return out
