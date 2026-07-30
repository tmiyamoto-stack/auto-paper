"""Check R（モデル仕様突合＝Methods記載の推定式↔コード実装）。

## なぜ必要か

check B（Methods↔コード突合）は「実データのフィルタ/除外/コーディング手続き」に
スコープが限定されており、**モデル式そのもの**（どの変数を回帰に投入したか、
どの固定効果を使ったか）は対象外である（DESIGN.md も明記済み）。check Q
（モデル診断）も収束・推定可能性・宣言診断の実行照合であって、「掲載した推定式が
実際にコードで推定された式と同じか」は照合していない。

このギャップが実際に起きた欠陥を見逃した: 2026-07-28の外部レビューで、ある論文の
event study が「onset起点の相対時点ダミー回帰」とMethodsに記載されていたにも
かかわらず、実装は翌年・同年・前年の所得減少指標を同時投入する別のモデル
（recurrent-treatment型）だった。onset変数は計算されていたが一度も回帰式に
使われていなかった。check B・check Q のどちらの決定的規則にも、この種の不一致を
検出する仕組みが無かった。

## 何を決定的に照合するか

Methods記載の推定式（`model_specs`: outcome・regressors・fixed_effects の集合）と、
コードが実際に推定したモデル（`model_implementations`: 同じ形）を、`id` で対応づけて
集合として突合する。regressors/fixed_effects の集合が一致しない、または outcome が
異なれば、原稿の記述とコードが同じモデルを指していないことを意味し CRITICAL FAIL。

`model_specs` は Methods 記載から機械的に抽出する（可能な限り、コードを見た
生成エージェントとは別の経路で）。`model_implementations` は実際の推定コード
（例: `PanelOLS(y, X[...], entity_effects=.., time_effects=..)` 呼び出し）から
静的/AST検査等で抽出する。いずれも人手の要約に頼らないことが望ましいが、本チェック
自体は集合の突合のみを担い、抽出方法は上流の責務とする。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity

_RULE = "t1.model.spec_correspondence"


def check_r_model_spec(model_specs: list[dict] | None,
                       model_implementations: list[dict] | None) -> list[Finding]:
    findings: list[Finding] = []

    if not model_specs and not model_implementations:
        return [
            Finding("R", Status.INCOMPLETE, Severity.CRITICAL,
                    "モデル仕様の記載と実装が共に空で突合不能",
                    "model_specs=[] model_implementations=[]",
                    rule_id=_RULE, taxonomy_id="B")
        ]

    model_specs = model_specs or []
    model_implementations = model_implementations or []
    impl_by_id = {m["id"]: m for m in model_implementations}

    for spec in model_specs:
        mid = spec["id"]
        impl = impl_by_id.get(mid)
        if impl is None:
            findings.append(
                Finding("R", Status.FAIL, Severity.CRITICAL,
                        f"Methods記載のモデルに対応する実装が見つからない: {mid}",
                        f"spec {mid}: regressors={sorted(spec['regressors'])}",
                        variable=mid, rule_id=_RULE, taxonomy_id="B")
            )
            continue

        mismatches = []
        if spec["outcome"] != impl["outcome"]:
            mismatches.append(f"outcome claim='{spec['outcome']}' impl='{impl['outcome']}'")
        claimed_reg = set(spec["regressors"])
        impl_reg = set(impl["regressors"])
        if claimed_reg != impl_reg:
            only_claimed = sorted(claimed_reg - impl_reg)
            only_impl = sorted(impl_reg - claimed_reg)
            mismatches.append(
                f"regressors mismatch: Methods記載のみ={only_claimed} "
                f"実装のみ={only_impl}"
            )
        claimed_fe = set(spec.get("fixed_effects", []))
        impl_fe = set(impl.get("fixed_effects", []))
        if claimed_fe != impl_fe:
            mismatches.append(
                f"fixed_effects mismatch: 記載={sorted(claimed_fe)} 実装={sorted(impl_fe)}"
            )

        if mismatches:
            findings.append(
                Finding("R", Status.FAIL, Severity.CRITICAL,
                        f"Methods記載のモデル仕様がコードの実装と不一致: {mid}",
                        "; ".join(mismatches) + f" | {impl.get('evidence', '')}",
                        variable=mid, rule_id=_RULE, taxonomy_id="B")
            )
        else:
            findings.append(
                Finding("R", Status.PASS, Severity.CRITICAL,
                        f"モデル仕様は記載通り実装: {mid}",
                        f"regressors={sorted(claimed_reg)}",
                        variable=mid, rule_id=_RULE, taxonomy_id="B")
            )

    # 方向2: 実装 → 記載（記載されていない主要モデルが結果に紛れ込んでいないか）
    claimed_ids = {spec["id"] for spec in model_specs}
    for impl in model_implementations:
        if impl["id"] not in claimed_ids:
            findings.append(
                Finding("R", Status.FAIL, Severity.MAJOR,
                        f"コードで推定されたモデルがMethods未記載: {impl['id']}",
                        impl.get("evidence", ""),
                        variable=impl["id"], rule_id=_RULE, taxonomy_id="B")
            )

    return findings
