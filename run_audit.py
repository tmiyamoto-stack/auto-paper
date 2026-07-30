# -*- coding: utf-8 -*-
"""工程5（監査）ドライバ: 任意ドメインの表形式データに Tier1 監査を実走する。

監査ロジックは一切ここに書かない。共有コアの `run_tier1_generic` を呼ぶだけであり、
本ファイルの責務は次の4点に限られる。

  1. 共有コアを解決して import 可能にする（`core.ensure_core_importable`）
  2. ドメイン参照パックと成果物から、コアへ渡す入力を組み立てる
  3. **供給できなかった入力に対応するチェックを明示的に INCOMPLETE として報告する**
  4. 結果と coverage を出力し、fail-closed で終了コードを返す

## 3 について（2026-07-30 の外部レビューで発見された欠陥への対処）

コアの `run_tier1_generic` は optional kwargs が未供給のチェックを「意図的スキップ」
として扱い、finding を1件も出さない。したがって素朴にドライバを書くと、
19チェック中2つ（A/B）しか走っていないのに `PASS=2 FAIL=0 INCOMPLETE=0` で
**exit 0** を返す。これは本スキルが構造的に防ぐと宣言している
「監査を実行せずに成功して見える」経路そのものだった（実測で確認済み）。

そこで本ドライバは、`config.yaml` の `profiles.default.checks` に列挙された
チェック ID のうち **finding が1件も出なかったもの**を「未実行」とみなし、
理由付きの INCOMPLETE finding を合成して報告する。結果として、入力を揃えない限り
exit 0 にはならない。`checks` の列挙は装飾ではなく実際に読まれる。

終了コード:
  0 = 全チェックが走り、FAIL も INCOMPLETE も無い
  1 = FAIL または INCOMPLETE が1件以上（未実行チェックを含む＝人間の確認が必要）
  2 = 監査を実行できなかった（コア未解決・コア曖昧・入力欠落・ドメイン未宣言・
      成果物の形式不正・コア側の実行時エラー）

「実行できなかった」を 1 と区別するのは重要である。監査が動かなかったことを
「不合格」と同じ扱いにすると、設定ミスを検出結果と読み違える。したがって
**想定外の例外も 2 に正規化する**（traceback で 1 を返さない）。

使い方:
    python3 run_audit.py --run-dir <成果物ディレクトリ> --domain general \
        [--data-csv path] [--codebook path] [--user-dictionary path] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

import core
import domain as domain_mod

# 未供給時に「どの成果物を用意すれば走るか」を人間に示すための対応表。
# config の checks に載っているのに finding が出なかったチェックは、この理由付きで
# INCOMPLETE として報告される。
CHECK_REQUIREMENTS = {
    "A": "01_data/variable_codebook.json と data_profile（またはユーザー辞書）",
    "B": "03_results/methods_claims.json と code_filters.json",
    "D": "03_results/sap_ranges.json の plausible_ranges / impossible_ranges（観測値はプロファイルから導出）",
    "E": "03_results/sap_ranges.json の missing_rates と missingness_reported",
    "G": "03_results/sap_ranges.json の sample_type と 04_manuscript の限界セクション本文",
    "H": "03_results/sap_ranges.json の inference.attrition（残存/脱落の baseline）",
    "I": "03_results/sap_ranges.json の immortal_subjects と exposure_type（日付列）",
    "J": "03_results/sap_ranges.json の labels_by_source（多ソース/多時点データのみ）",
    "K": "03_results/flow.json と 03_results/sap_ranges.json の claimed_ns",
    "L": "打ち切り候補（data_profile の censored_candidates）と censored_declared_handled 宣言",
    "M": "03_results/bibliography.json（DOI/PMID 付き参照リスト）",
    "O": "03_results/sap_ranges.json の study_design と 04_manuscript の Results/Conclusions 本文",
    "P": "03_results/sap_ranges.json の inference.prereg（事前登録との突合）",
    "Q": "03_results/sap_ranges.json の inference.model",
    "R": "03_results/sap_ranges.json の inference.model_spec",
    "S": "04_manuscript の各セクション本文（style_sections）",
    "T": "03_results/sap_ranges.json の inference.cluster",
    "U": "03_results/sap_ranges.json の declared_units と observed_unit_center",
    "W": "03_results/sap_ranges.json の inference.weights（IPW 重みベクトル）",
    "X": "03_results/sap_ranges.json の inference.reference_groups（参照/対照群の構成。曝露者混入の検出）",
    "Y": "03_results/sap_ranges.json の inference.reported_numbers と inference.results_values（原稿数値が results に遡れるかの照合）",
}


class AuditNotRun(Exception):
    """監査を実行できなかった（終了コード 2 に対応）。"""


def _p(run_dir: str, *parts: str) -> str:
    return os.path.join(run_dir, *parts)


def _load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise AuditNotRun(f"JSON の形式が不正: {path} — {e}") from e


def _observed_from_profile(data_profile: dict, codebook_path: str) -> dict:
    """check D の観測値をデータプロファイルから導出する。

    旧実装は `sap_ranges.json` の `observed`（＝解析エージェントの自己申告）を
    使っていたが、それでは「宣言値域 vs 宣言観測値」の照合になり、両辺とも同じ
    成果物由来になる。転記ミスこそ本スキルが消すと約束したクラスなので、
    観測値は生データのプロファイル（決定的）から取る。

    プロファイルは列ごとの min/max を持つ。値域逸脱の検出には両端で十分である
    （min か max が範囲外なら FAIL、両方が内側なら全値が内側）。
    """
    cols = (data_profile or {}).get("columns", {})
    try:
        with open(codebook_path, encoding="utf-8") as fh:
            variables = json.load(fh).get("variables", [])
    except (OSError, ValueError):
        return {}
    observed: dict[str, list] = {}
    for v in variables:
        col = cols.get(v.get("source_column"))
        if not col:
            continue
        vals = [x for x in (col.get("min"), col.get("max"))
                if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if vals:
            observed[v["name"]] = sorted(set(vals))
    return observed


def _synthesize_unrun(findings, coverage, declared_checks: list[str],
                      Finding, Status, Severity):
    """実行された形跡が無い宣言済みチェックを INCOMPLETE として明示する。

    「finding が無い＝未実行」と単純化してはならない。入力が空集合のとき、
    チェックは実行されたうえで finding 0 件・coverage proof ありになる
    （実測で E/J/L/S がこの形になった）。これを未実行と報告すると偽陽性になる。
    したがって **finding または coverage proof のどちらかがあれば「実行された」**
    とみなす。
    """
    seen = {f.check_id for f in findings}
    seen |= {c.check_id for c in (coverage or [])}
    out = []
    for cid in declared_checks:
        if cid in seen:
            continue
        out.append(Finding(
            cid, Status.INCOMPLETE, Severity.CRITICAL,
            f"チェック {cid} は入力未供給のため実行されていない",
            f"必要な入力: {CHECK_REQUIREMENTS.get(cid, '(未定義)')}。"
            f"供給が無いままでは監査されないため INCOMPLETE として報告する"
            f"（サイレントスキップ禁止）。",
            variable=None))
    return out


def _build(args) -> dict:
    """入力を集めてコアを呼ぶ。失敗はすべて AuditNotRun に正規化する。"""
    run_dir = os.path.abspath(os.path.expanduser(args.run_dir))
    if not os.path.isdir(run_dir):
        raise AuditNotRun(f"--run-dir が存在しない: {run_dir}")

    try:
        core_path = core.ensure_core_importable(args.core)
    except (core.CoreNotFound, core.CoreAmbiguous) as e:
        raise AuditNotRun(str(e)) from e

    cfg = core.load_config()
    dom = args.domain or cfg.get("domain")

    codebook = args.codebook or _p(run_dir, "01_data", "variable_codebook.json")
    methods_claims = _p(run_dir, "03_results", "methods_claims.json")
    code_filters = _p(run_dir, "03_results", "code_filters.json")
    for label, path in (("variable_codebook.json", codebook),
                        ("methods_claims.json", methods_claims),
                        ("code_filters.json", code_filters)):
        if not os.path.exists(path):
            raise AuditNotRun(f"必須成果物が無い: {label} ({path})")

    profile_path = _p(run_dir, "01_data", "data_profile.json")
    data_profile = _load_json(profile_path)
    data_csv = args.data_csv
    if data_csv and not os.path.exists(data_csv):
        raise AuditNotRun(f"--data-csv が存在しない: {data_csv}")
    if data_csv is None and data_profile is None:
        raise AuditNotRun("--data-csv も 01_data/data_profile.json も無く、一次ソースを取得できない")
    # profile-only モード: コアは data_csv_path を無条件に hash するため空文字を渡せない。
    # このモードの一次ソースはプロファイル自身なので、その実ファイルを provenance として渡す。
    provenance_path = data_csv or profile_path

    user_dict = args.user_dictionary or _p(run_dir, "01_data", "user_dictionary.json")
    user_dict = user_dict if os.path.exists(user_dict) else None

    sap = _load_json(_p(run_dir, "03_results", "sap_ranges.json"), {}) or {}
    flow = _load_json(_p(run_dir, "03_results", "flow.json"))
    biblio = _load_json(_p(run_dir, "03_results", "bibliography.json"))

    try:
        pack = domain_mod.build_audit_kwargs(
            dom,
            sap_impossible_ranges=sap.get("impossible_ranges"),
            sap_plausible_ranges=sap.get("plausible_ranges"),
            declared_units=sap.get("declared_units"),
            sap_plausible_by_unit=sap.get("plausible_by_unit"),
        )
    except domain_mod.DomainError as e:
        raise AuditNotRun(str(e)) from e

    from audit.tier1.runner import run_tier1_generic
    from pipeline.profile_data import profile_csv

    if data_profile is None:
        data_profile = profile_csv(data_csv)

    # 観測値は自己申告ではなくプロファイル由来（決定的）
    observed = _observed_from_profile(data_profile, codebook)
    pack["unranged_variables"] = sorted(
        k for k in observed
        if k not in pack["outlier_ranges"] and k not in pack["impossible_ranges"])

    inference = sap.get("inference") or {}
    result = run_tier1_generic(
        codebook_path=codebook,
        data_csv_path=provenance_path,
        methods_claims_path=methods_claims,
        code_filters_path=code_filters,
        user_dictionary_path=user_dict,
        data_profile=data_profile,
        outlier_observed=observed or None,
        outlier_ranges=pack["outlier_ranges"] or None,
        impossible_ranges=pack["impossible_ranges"] or None,
        declared_units=pack["declared_units"] or None,
        observed_unit_center=sap.get("observed_unit_center"),
        unit_plausible=pack["unit_plausible"] or None,
        flow=flow,
        claimed_ns=sap.get("claimed_ns"),
        bibliography=biblio,
        censored_by_column=sap.get("censored_by_column"),
        censored_declared_handled=set(sap.get("censored_declared_handled") or []) or None,
        immortal_subjects=sap.get("immortal_subjects"),
        immortal_exposure_type=sap.get("immortal_exposure_type"),
        missing_rates=sap.get("missing_rates"),
        missingness_reported=set(sap.get("missingness_reported") or []) or None,
        labels_by_source=sap.get("labels_by_source"),
        section_texts=sap.get("section_texts"),
        study_design=sap.get("study_design"),
        sample_type=sap.get("sample_type"),
        limitations_text=sap.get("limitations_text"),
        inference=inference or None,
        style_sections=sap.get("style_sections"),
    )
    result["_core_path"] = core_path
    result["_domain"] = pack["domain"]
    result["_pack"] = pack
    result["_declared_checks"] = (cfg.get("profiles", {}).get("default", {}).get("checks") or [])
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="任意ドメインの表形式データに Tier1 監査を実走する")
    ap.add_argument("--run-dir", required=True, help="成果物ディレクトリ")
    ap.add_argument("--domain", help="clinical | survey | general")
    ap.add_argument("--data-csv", help="生データ CSV")
    ap.add_argument("--codebook", help="variable_codebook.json")
    ap.add_argument("--user-dictionary", help="user_dictionary.json")
    ap.add_argument("--json", dest="json_out", help="findings を JSON で書き出す")
    ap.add_argument("--core", help="共有コアのパスを明示する")
    args = ap.parse_args(argv)

    try:
        result = _build(args)
    except AuditNotRun as e:
        sys.stderr.write(f"[監査を実行できない] {e}\n")
        return 2
    except Exception as e:  # noqa: BLE001 — 想定外も 2 に正規化する（1 に化けさせない）
        sys.stderr.write(f"[監査を実行できない] 想定外のエラー: {type(e).__name__}: {e}\n")
        sys.stderr.write(traceback.format_exc())
        return 2

    from audit.tier1.findings import Finding, Status, Severity

    findings = list(result["findings"])
    unrun = _synthesize_unrun(findings, result.get("coverage"), result["_declared_checks"],
                              Finding, Status, Severity)
    findings += unrun

    n_fail = sum(1 for f in findings if f.status is Status.FAIL)
    n_inc = sum(1 for f in findings if f.status is Status.INCOMPLETE)
    n_pass = sum(1 for f in findings if f.status is Status.PASS)

    print("=" * 78)
    print(f"共有コア : {result['_core_path']}")
    print(f"ドメイン : {result['_domain']}（参照データの選択のみ。チェック集合は全ドメイン共通）")
    print("=" * 78)
    for f in findings:
        if f.status is Status.PASS:
            continue
        print(f"[{f.status.value.upper()}/{f.severity.value}] {f.summary}")
        if f.evidence:
            print(f"    {f.evidence[:190]}")

    # coverage proof（コアが返すのに従来は捨てていた。走った/走らなかったの唯一の証跡）
    print("-" * 78)
    print("coverage:")
    for c in result.get("coverage", []):
        checked = getattr(c, "items_checked", []) or []
        inc = getattr(c, "incomplete", []) or []
        print(f"  check {c.check_id}: 照合 {len(checked)} 件 / 未照合 {len(inc)} 件")
    if unrun:
        print(f"  未実行チェック（入力未供給）: {', '.join(sorted(f.check_id for f in unrun))}")

    print("=" * 78)
    print(f"PASS={n_pass} FAIL={n_fail} INCOMPLETE={n_inc} critical_fail={result['critical_fail']}")

    warn = domain_mod.unranged_warning(result["_pack"])
    if warn:
        print(warn)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({
                "core_path": result["_core_path"],
                "domain": result["_domain"],
                "critical_fail": result["critical_fail"],
                "counts": {"pass": n_pass, "fail": n_fail, "incomplete": n_inc},
                "unrun_checks": sorted(f.check_id for f in unrun),
                "unranged_variables": result["_pack"]["unranged_variables"],
                "coverage": [
                    {"check_id": c.check_id,
                     "files_read": [list(x) for x in (getattr(c, "files_read", []) or [])],
                     "items_checked": list(getattr(c, "items_checked", []) or []),
                     "incomplete": list(getattr(c, "incomplete", []) or [])}
                    for c in result.get("coverage", [])
                ],
                "findings": [
                    {"check_id": f.check_id, "status": f.status.value,
                     "severity": f.severity.value, "summary": f.summary,
                     "evidence": f.evidence, "variable": f.variable}
                    for f in findings
                ],
            }, fh, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"findings を書き出した: {args.json_out}")

    return 1 if (n_fail or n_inc) else 0


if __name__ == "__main__":
    raise SystemExit(main())
