"""Check T（クラスタロバスト標準誤差 ↔ 個人ID の整合）。

共同研究者レビュー3 §4.2 の提案。Fable・Codex Sol の両レビューが「3ゲート中もっとも
筋がよい」と評価した規則で、判定はすべて**算術と文字通りの矛盾**に収まる。

## 何を検出するか（実バグのクラス）

個人単位クラスタロバスト SE を宣言しているのに、実際には

- 渡したクラスタ変数が宣言と違う（ID 列の取り違え）
- 解析行のクラスタ ID が欠測（その行にクラスタリングが適用できていない）
- クラスタベクトル長が解析行数と一致しない（merge 事故）
- 独立クラスタが2未満（クラスタロバスト SE が定義不能）

といった状態は、**宣言と実装の文字通りの矛盾**であり決定的に検出できる。とくに
「パネルだと宣言したのに全クラスタサイズが1」は、ID 列の取り違えや merge 事故で
クラスタリングが黙って独立化した典型的な実バグで、推定 SE を過小にする。

## model frame に限定する（Codex Sol 指摘）

元データに ID 欠測があっても、実際の model frame ではその行が既に除外されている
ことがある。**元データ全体を検査すると偽陽性**になるため、検査対象は「実際に fit に
渡された行」に限定する。

## クラスタ数の下限は決定的にしない（両レビュー一致）

「最低30/50クラスタ」のような普遍閾値は、少数クラスタでも CR2・Satterthwaite 補正・
wild cluster bootstrap を適切に用いた正しい推論を落とす。クラスタ数は
`t1.cluster.finite_sample_risk`（surfacing/MAJOR）に隔離し、SAP 宣言の下限がある
場合のみそれと突合する。

## singleton を一律 FAIL にしない（Codex Sol 指摘）

横断解析で1人1行のデータに個人単位 sandwich SE を使えば全クラスタが singleton に
なるが、それ自体は矛盾ではない。FAIL にするのは **`rationale="repeated_measures"`
（反復測定を理由にクラスタリングすると宣言）なのに全クラスタが singleton** という
場合に限る。これは宣言されたパネル構造がデータに存在しないという文字通りの矛盾。
"""
from __future__ import annotations

import collections

from .findings import Finding, Status, Severity

_RULE_INT = "t1.cluster.model_frame_integrity"
_RULE_FIN = "t1.cluster.finite_sample_risk"

# 有限標本補正なしのクラスタロバスト推論で慣行的に目安とされるクラスタ数
# （Cameron & Miller 2015, J Hum Resour）。恣意性があるため surfacing 限定。
_CLUSTER_COUNT_HINT = 40


def check_t_cluster(cluster_ids: dict[str, list] | None,
                    cluster_declared: dict[str, dict] | None = None,
                    implemented_se_type: dict[str, str] | None = None,
                    model_frame_rows: dict[str, int] | None = None,
                    cluster_count_hint: int = _CLUSTER_COUNT_HINT) -> list[Finding]:
    """クラスタSE の宣言と model frame の実態を突合する。

    `cluster_ids`: {analysis_id: 解析に実際に渡した行ごとのクラスタID（欠測は None）}
    `cluster_declared`: {analysis_id: {"cluster_var": str, "se_type": str,
        "rationale": "repeated_measures"|"design_cluster", "n_waves": int|None,
        "min_clusters": int|None}}
    `implemented_se_type`: {analysis_id: 実行 trace 由来の SE 種別}
    `model_frame_rows`: {analysis_id: 実際に fit に渡した行数}
    """
    if cluster_ids is None:
        if cluster_declared:
            return [Finding("T", Status.INCOMPLETE, Severity.CRITICAL,
                "クラスタSEが宣言されているがクラスタベクトル未提供で監査不能",
                f"cluster_declared={sorted(cluster_declared)}, cluster_ids=None",
                rule_id=_RULE_INT, taxonomy_id="L")]
        return []

    cluster_declared = cluster_declared or {}
    implemented_se_type = implemented_se_type or {}
    model_frame_rows = model_frame_rows or {}
    findings: list[Finding] = []

    for aid in sorted(cluster_ids):
        ids = cluster_ids[aid]
        decl = cluster_declared.get(aid, {})

        # --- SE 種別の宣言↔実装（文字通りの突合） ---
        want_se = decl.get("se_type")
        got_se = implemented_se_type.get(aid)
        if want_se and got_se and want_se != got_se:
            findings.append(Finding("T", Status.FAIL, Severity.CRITICAL,
                f"宣言したSE種別と実装が不一致: {aid}",
                f"analysis={aid}, 宣言={want_se}, 実装={got_se}",
                variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))

        # --- クラスタベクトル長 ↔ model frame 行数 ---
        n_rows = model_frame_rows.get(aid)
        if n_rows is not None and n_rows != len(ids):
            findings.append(Finding("T", Status.FAIL, Severity.CRITICAL,
                f"クラスタベクトル長が解析行数と不一致: {aid}",
                f"analysis={aid}, model_frame行数={n_rows}, クラスタ長={len(ids)}"
                "（merge 事故でクラスタが行にずれて割り当たっている疑い）",
                variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))

        # --- 解析行のクラスタID欠測（model frame 限定で検査） ---
        n_missing = sum(1 for x in ids if x is None or x == "")
        if n_missing:
            findings.append(Finding("T", Status.FAIL, Severity.CRITICAL,
                f"解析行にクラスタID欠測があり宣言したクラスタリングを適用できない: {aid}",
                f"analysis={aid}, 欠測行={n_missing}/{len(ids)}",
                variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))
            continue

        sizes = collections.Counter(ids)
        n_clusters = len(sizes)

        # --- 独立クラスタ2未満（クラスタロバストSEが定義不能） ---
        if n_clusters < 2:
            findings.append(Finding("T", Status.FAIL, Severity.CRITICAL,
                f"独立クラスタが2未満でクラスタロバストSEを定義できない: {aid}",
                f"analysis={aid}, 独立クラスタ数={n_clusters}, 行数={len(ids)}",
                variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))
            continue

        # --- 反復測定を宣言したのに全クラスタが singleton ---
        max_size = max(sizes.values())
        if decl.get("rationale") == "repeated_measures" and max_size == 1:
            findings.append(Finding("T", Status.FAIL, Severity.CRITICAL,
                f"反復測定を理由にクラスタリングと宣言しているが全クラスタが単一観測: {aid}",
                f"analysis={aid}, 独立クラスタ数={n_clusters}=行数={len(ids)}"
                "（ID列の取り違え・merge 事故でクラスタリングが独立化した疑い）",
                variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))
            continue

        # --- クラスタサイズが宣言波数を超える（ID重複・merge爆発） ---
        n_waves = decl.get("n_waves")
        if n_waves and max_size > n_waves:
            findings.append(Finding("T", Status.FAIL, Severity.CRITICAL,
                f"最大クラスタサイズが宣言波数を超過: {aid}",
                f"analysis={aid}, 最大クラスタサイズ={max_size} > 宣言波数={n_waves}"
                "（ID重複・merge 爆発の疑い）",
                variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))
            continue

        findings.append(Finding("T", Status.PASS, Severity.CRITICAL,
            f"クラスタSEの宣言とmodel frameは整合: {aid}",
            f"analysis={aid}, 行数={len(ids)}, 独立クラスタ数={n_clusters}, "
            f"最大クラスタサイズ={max_size}",
            variable=aid, rule_id=_RULE_INT, taxonomy_id="L"))

        # --- 有限標本リスク（surfacing。普遍閾値でハードFAILにしない） ---
        floor = decl.get("min_clusters")
        threshold = floor if floor is not None else cluster_count_hint
        source = "SAP宣言" if floor is not None else "既定目安"
        if n_clusters < threshold:
            findings.append(Finding("T", Status.FAIL, Severity.MAJOR,
                f"独立クラスタ数が少なく有限標本補正の要否を検討すべき: {aid}",
                f"analysis={aid}, 独立クラスタ数={n_clusters} < {threshold}({source})。"
                "※少数クラスタでも CR2・Satterthwaite 補正・wild cluster bootstrap を"
                "用いれば妥当な推論は可能であり、これは欠陥の確定ではない。"
                "補正の要否は Tier2/人間が判定する材料",
                variable=aid, rule_id=_RULE_FIN, taxonomy_id="L"))

    return findings
