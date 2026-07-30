from __future__ import annotations

import hashlib
import json

from .codebook import load_codebook
from .check_a_coding import check_a
from .check_a_generic import check_a_generic, load_generic_codebook
from .check_b_methods_code import check_b
from .check_d_outliers import check_d
from .check_i_immortal import check_i_immortal
from .check_k_flow import check_k
from .check_l_censored import check_l_censored
from .check_m_citations import check_m, check_m_metadata
from .check_j_harmonization import check_j
from .check_e_missingness import check_e_missingness
from .check_u_units import check_u_units
from .check_o_overstatement import check_o_overstatement
from .check_g_generalizability import check_g_generalizability
from .check_w_weights import check_w_weights
from .check_e_mechanism import check_e_mechanism
from .check_h_attrition import check_h_attrition
from .check_s_style import check_s_style
from .check_t_cluster import check_t_cluster
from .check_p_prereg import check_p_prereg
from .check_q_model import check_q_model
from .check_r_model_spec import check_r_model_spec
from .check_x_reference_contamination import check_x_reference_contamination
from .check_y_number_provenance import check_y_number_provenance
from .check_e_mechanism import check_e_declared_vs_implemented
from .findings import CoverageProof, Finding, Status, Severity


# study_design が参照/対照/pre-period 群を本質的に要する設計。これらの宣言下で
# reference_groups が未供給なら、check X を fail-closed で INCOMPLETE にする（Fable 指摘 C-1）。
_REFERENCE_DESIGNS = frozenset({
    "event_study", "did", "difference_in_differences",
    "dose_response", "case_control", "self_controlled",
})


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _run_optional_checks(findings: list, coverage: list,
                         outlier_observed, outlier_ranges,
                         flow, claimed_ns,
                         bibliography, citation_fetcher,
                         labels_by_wave,
                         impossible_ranges=None,
                         censored_by_column=None, censored_declared_handled=None,
                         immortal_subjects=None, immortal_exposure_type=None,
                         missing_rates=None, missingness_reported=None,
                         declared_units=None, observed_unit_center=None, unit_plausible=None,
                         bibliography_metadata=None, metadata_fetcher=None,
                         labels_by_source=None,
                         section_texts=None, study_design=None,
                         sample_type=None, limitations_text=None) -> None:
    """D/K/M/J/L/I のオプション配線（jastis/generic 共有・in-place 追記）。

    Fix J: check_d に impossible_ranges を通す（生理的にありえない値→CRITICAL）。
    Fix D/F: 片側だけ設定された（half-configured）オプション対はサイレントに
    スキップせず INCOMPLETE を出す（fail-closed）。両側 None の完全未設定のみ
    真のスキップ（finding 無し）。

    L（打ち切り値/検出限界）: censored_by_column が主入力。提供時は
    declared を欠くと空集合扱いで実行し、未宣言列を FAIL にする（打ち切りの
    無宣言＝危険なので INCOMPLETE ではなく FAIL）。declared のみ提供（プロファイル
    無し）は half-configured で INCOMPLETE。
    I（不死時間）: immortal_subjects 提供時に実行。exposure_type は None のとき
    保守的に "time_fixed"（最も違反を検出しやすい）を既定にする。"""
    # D（外れ値）: 両側設定で実行。片側のみ設定は監査不能で INCOMPLETE/CRITICAL。
    if outlier_observed is not None and outlier_ranges is not None:
        findings += check_d(outlier_observed, outlier_ranges, impossible_ranges)
        coverage.append(CoverageProof("D", files_read=[], items_checked=sorted(outlier_observed), incomplete=[]))
    elif outlier_observed is not None or outlier_ranges is not None:
        findings.append(Finding("D", Status.INCOMPLETE, Severity.CRITICAL,
            "外れ値監査の設定が不完全（observed/ranges の一方のみ指定）で監査不能",
            f"outlier_observed={'set' if outlier_observed is not None else 'None'}, "
            f"outlier_ranges={'set' if outlier_ranges is not None else 'None'}"))
        coverage.append(CoverageProof("D", files_read=[], items_checked=[], incomplete=["outlier"]))

    if flow is not None:
        findings += check_k(flow, claimed_ns or {})
        stage_labels = sorted(s["label"] for s in flow.get("stages", []))
        coverage.append(CoverageProof("K", files_read=[], items_checked=stage_labels, incomplete=[]))

    # M（引用実在）: 非空 bibliography に fetcher が無ければ監査不能で INCOMPLETE/CRITICAL
    # （Fix D）。空 bibliography + fetcher は従来通り check_m（実質 no-op）。
    if bibliography:
        if citation_fetcher is not None:
            findings += check_m(bibliography, citation_fetcher)
            coverage.append(CoverageProof("M", files_read=[],
                                           items_checked=sorted(ref.get("id", "?") for ref in bibliography),
                                           incomplete=[]))
        else:
            findings.append(Finding("M", Status.INCOMPLETE, Severity.CRITICAL,
                "引用実在検証器(fetcher)未提供で監査不能",
                f"bibliography={len(bibliography)}件 だが citation_fetcher=None"))
            coverage.append(CoverageProof("M", files_read=[], items_checked=[],
                                           incomplete=sorted(ref.get("id", "?") for ref in bibliography)))
    elif bibliography is not None and citation_fetcher is not None:
        findings += check_m(bibliography, citation_fetcher)
        coverage.append(CoverageProof("M", files_read=[], items_checked=[], incomplete=[]))

    if labels_by_wave is not None:
        findings += check_j(labels_by_wave)
        coverage.append(CoverageProof("J", files_read=[], items_checked=sorted(labels_by_wave), incomplete=[]))

    # L（打ち切り値/検出限界）: censored_by_column が主入力。declared のみは half-configured。
    if censored_by_column is not None:
        findings += check_l_censored(censored_by_column, censored_declared_handled or set())
        coverage.append(CoverageProof("L", files_read=[],
                                       items_checked=sorted(censored_by_column), incomplete=[]))
    elif censored_declared_handled is not None:
        findings.append(Finding("L", Status.INCOMPLETE, Severity.CRITICAL,
            "打ち切り監査の設定が不完全（declared のみ・プロファイル未提供）で監査不能",
            f"censored_declared_handled={sorted(censored_declared_handled)}"))
        coverage.append(CoverageProof("L", files_read=[], items_checked=[], incomplete=["censored"]))

    # I（不死時間バイアス）: subjects 提供時に実行。exposure_type 既定は保守的に time_fixed。
    if immortal_subjects is not None:
        et = immortal_exposure_type or "time_fixed"
        findings += check_i_immortal(immortal_subjects, et)
        coverage.append(CoverageProof("I", files_read=[],
                                       items_checked=[f"n_subjects={len(immortal_subjects)}"], incomplete=[]))

    # E（欠測率↔Methods報告）: missing_rates が主入力。reported のみは half-configured で INCOMPLETE。
    if missing_rates is not None:
        findings += check_e_missingness(missing_rates, missingness_reported or set())
        coverage.append(CoverageProof("E", files_read=[],
                                       items_checked=sorted(missing_rates), incomplete=[]))
    elif missingness_reported is not None:
        findings.append(Finding("E", Status.INCOMPLETE, Severity.CRITICAL,
            "欠測率監査の設定が不完全（reported のみ・欠測率算出未提供）で監査不能",
            f"missingness_reported={sorted(missingness_reported)}"))
        coverage.append(CoverageProof("E", files_read=[], items_checked=[], incomplete=["missingness"]))

    # U（単位混在）: declared_units が主入力。観測中央値/基準域欠如は check_u_units 内で INCOMPLETE。
    if declared_units is not None:
        findings += check_u_units(declared_units, observed_unit_center, unit_plausible or {})
        coverage.append(CoverageProof("U", files_read=[],
                                       items_checked=sorted(declared_units), incomplete=[]))

    # M（引用メタデータ一致）: bibliography_metadata に fetcher が無ければ INCOMPLETE（half-configured）。
    if bibliography_metadata:
        if metadata_fetcher is not None:
            findings += check_m_metadata(bibliography_metadata, metadata_fetcher)
            coverage.append(CoverageProof("M", files_read=[],
                                           items_checked=sorted(str(r.get("id", "?")) for r in bibliography_metadata),
                                           incomplete=[]))
        else:
            findings.append(Finding("M", Status.INCOMPLETE, Severity.CRITICAL,
                "引用メタデータ照合器(metadata_fetcher)未提供で監査不能",
                f"bibliography_metadata={len(bibliography_metadata)}件 だが metadata_fetcher=None"))
            coverage.append(CoverageProof("M", files_read=[], items_checked=[],
                                           incomplete=sorted(str(r.get("id", "?")) for r in bibliography_metadata)))

    # J（多施設/多ソース ハーモナイゼーション）: labels_by_source 提供時に check_j を条件付き有効化。
    if labels_by_source is not None:
        findings += check_j(labels_by_source)
        coverage.append(CoverageProof("J", files_read=[], items_checked=sorted(labels_by_source), incomplete=[]))

    # O（解釈の誇張＝セミ決定的サーフェシング, MAJOR）: study_design 宣言が主入力。
    # 宣言時に check_o を実行し、観察研究の因果含意語を人間/Tier2・3 判定者に surface。
    # section_texts 欠如は check_o 側で INCOMPLETE（fail-closed、サイレント PASS 禁止）。
    # MAJOR なので critical_fail はトリップしない（ハードブロックせず surfacing のみ）。
    if study_design is not None:
        findings += check_o_overstatement(section_texts, study_design)
        coverage.append(CoverageProof("O", files_read=[],
                                       items_checked=sorted(section_texts) if section_texts else [],
                                       incomplete=[] if section_texts else ["section_texts"]))

    # G（一般化可能性スタンス＝セミ決定的サーフェシング, MAJOR）: sample_type 宣言が主入力。
    # 非母集団代表標本で限界に一般化言及が欠けていれば人間/Tier2・3 判定者に surface。
    # limitations_text 欠如は check_g 側で INCOMPLETE。MAJOR なので critical_fail 非トリップ。
    if sample_type is not None:
        findings += check_g_generalizability(sample_type, limitations_text)
        coverage.append(CoverageProof("G", files_read=[],
                                       items_checked=[sample_type],
                                       incomplete=[] if limitations_text is not None else ["limitations_text"]))


def _run_inference_checks(findings: list, coverage: list,
                          inference: dict | None,
                          style_sections: dict | None,
                          study_design: str | None = None,
                          section_texts: dict | None = None) -> None:
    """推論頑健性チェック（W: IPW重み / E: 欠測メカニズム / H: パネル脱落）と
    文体サーフェシング（S）のオプション配線。

    `inference` は宣言入力のバンドル（既存の1引数1入力方式では引数が膨れすぎるため）。
    受け付けるキーは以下。いずれも供給されなければその規則は実行されず、
    `registry.audit_counts` が `unmet_required` として穴を報告する
    （サイレント PASS ではなく、カバレッジの穴として可視化する設計）。

      ipw_weights, ipw_specs, weighting_declared,
      missingness_declared, missingness_handling, mnar_sensitivity,
      cc_covariate_only_justified, max_missing_rate,
      attrition_baseline, attrition_key_vars, attrition_handled,
      attrition_retention_by_group, is_panel
    """
    inference = inference or {}

    # W（IPW 重み）: weighting_declared=True かつ重み未供給は INCOMPLETE/CRITICAL。
    weights = inference.get("ipw_weights")
    weighting_declared = inference.get("weighting_declared")
    if weights is not None or weighting_declared:
        findings += check_w_weights(weights, inference.get("ipw_specs"),
                                    weighting_declared)
        coverage.append(CoverageProof("W", files_read=[],
                                      items_checked=sorted(weights) if weights else [],
                                      incomplete=[] if weights else ["ipw_weights"],
                                      rule_id="t1.weights.arithmetic", taxonomy_id="L"))

    # E（欠測メカニズム宣言↔実装）: 片側のみ宣言は check 側で INCOMPLETE。
    mech = inference.get("missingness_declared")
    hand = inference.get("missingness_handling")
    max_rate = inference.get("max_missing_rate")
    if mech is not None or hand is not None or max_rate is not None:
        mech_findings = check_e_mechanism(
            mech, hand,
            mnar_sensitivity=bool(inference.get("mnar_sensitivity", False)),
            cc_covariate_only_justified=bool(
                inference.get("cc_covariate_only_justified", False)),
            max_missing_rate=max_rate)
        findings += mech_findings
        coverage.append(CoverageProof(
            "E", files_read=[],
            items_checked=[f"mechanism={mech}", f"handling={hand}"],
            incomplete=[] if (mech and hand) else ["missingness_mechanism"],
            rule_id="t1.missingness.mechanism_implementation", taxonomy_id="E"))

    # H（パネル脱落）: is_panel=True で baseline 未供給は INCOMPLETE（fail-closed）。
    baseline = inference.get("attrition_baseline")
    is_panel = inference.get("is_panel")
    if baseline is not None or is_panel:
        findings += check_h_attrition(
            baseline,
            key_vars=inference.get("attrition_key_vars"),
            handled_declared=bool(inference.get("attrition_handled", False)),
            retention_by_group=inference.get("attrition_retention_by_group"),
            is_panel=is_panel)
        coverage.append(CoverageProof(
            "H", files_read=[],
            items_checked=sorted(baseline) if baseline else [],
            incomplete=[] if baseline else ["attrition_baseline"],
            rule_id="t1.attrition.differential", taxonomy_id="H"))

    # E（SAP宣言手法↔実行trace の直接突合）: 互換性判断とは別軸（CRITICAL）。
    dh = inference.get("missingness_declared_handling")
    ih = inference.get("missingness_implemented_handling")
    if dh is not None or ih is not None:
        findings += check_e_declared_vs_implemented(dh, ih)
        coverage.append(CoverageProof(
            "E", files_read=[], items_checked=[f"declared={dh}", f"implemented={ih}"],
            incomplete=[] if (dh and ih) else ["declared_vs_implemented"],
            rule_id="t1.missingness.declared_vs_implemented", taxonomy_id="E"))

    # T（クラスタSE↔個人ID整合）: 宣言 or クラスタベクトル供給時に実行。
    cids = inference.get("cluster_ids")
    cdecl = inference.get("cluster_declared")
    if cids is not None or cdecl:
        findings += check_t_cluster(cids, cdecl,
                                    inference.get("implemented_se_type"),
                                    inference.get("model_frame_rows"))
        coverage.append(CoverageProof(
            "T", files_read=[], items_checked=sorted(cids) if cids else [],
            incomplete=[] if cids else ["cluster_ids"],
            rule_id="t1.cluster.model_frame_integrity", taxonomy_id="L"))

    # P（事前登録整合）: マニフェスト供給 or 事前登録標榜時に実行。
    sap_a = inference.get("sap_analyses")
    exe_a = inference.get("executed_analyses")
    prereg = inference.get("preregistration_claimed")
    if sap_a is not None or exe_a is not None or prereg:
        findings += check_p_prereg(sap_a, exe_a,
                                   inference.get("sap_hash_expected"),
                                   inference.get("sap_hash_actual"),
                                   inference.get("adjusted_p_reported"),
                                   prereg)
        coverage.append(CoverageProof(
            "P", files_read=[],
            items_checked=[a.get("analysis_id") for a in (sap_a or [])],
            incomplete=[] if (sap_a and exe_a) else ["analysis_manifest"],
            rule_id="t1.prereg.analysis_set", taxonomy_id="B"))

    # Q（収束・推定可能性）: モデルtrace供給 or 回帰宣言時に実行。
    mtr = inference.get("model_trace")
    if mtr is not None or inference.get("regression_declared"):
        findings += check_q_model(mtr, inference.get("declared_terms"),
                                  inference.get("declared_diagnostics"),
                                  inference.get("regression_declared"))
        coverage.append(CoverageProof(
            "Q", files_read=[], items_checked=sorted(mtr) if mtr else [],
            incomplete=[] if mtr else ["model_trace"],
            rule_id="t1.model.estimability", taxonomy_id="L"))

    # R（モデル仕様突合）: Methods記載の推定式↔コード実装の回帰変数/固定効果突合。
    # check_b はフィルタ/除外手続きのみ対象、check_q は推定済みモデルの診断のみで
    # あり、どちらも「掲載式と実装式が同じモデルか」は照合しない（2026-07-28
    # 外部レビュー: onset-anchored event studyと記載しつつlead/current/lagモデルを
    # 実装していた不一致を、既存規則のどれも検出できなかった）。
    specs = inference.get("model_specs")
    impls = inference.get("model_implementations")
    if specs is not None or impls is not None:
        findings += check_r_model_spec(specs, impls)
        coverage.append(CoverageProof(
            "R", files_read=[],
            items_checked=sorted(s["id"] for s in specs) if specs else [],
            incomplete=[] if (specs and impls) else ["model_specs_or_implementations"],
            rule_id="t1.model.spec_correspondence", taxonomy_id="B"))

    # X（参照群/対照群の汚染）: 非曝露参照・pre-period に曝露済み観測が混入していないか。
    # check_b/check_r は「宣言どおりの手続き/式か」を見るが、比較の参照側の構成は見ない
    # （経済ショック event study の pre-trend ビンに 30.7% 曝露混入、加熱式タバコ頻度解析の
    # 272 person-wave 曝露者混入を、既存規則のどれも検出できなかった）。
    # fail-closed tripwire（Fable 指摘 C-1）: study_design が参照/対照を要する設計なのに
    # reference_groups 未供給なら、汚染検査が「実行されていない」ことを CRITICAL INCOMPLETE で
    # 可視化する（check R が旧専用スクリプトで機構を迂回され第3例を許した失敗の再発防止）。
    ref_groups = inference.get("reference_groups")
    if ref_groups is not None:
        findings += check_x_reference_contamination(ref_groups)
        coverage.append(CoverageProof(
            "X", files_read=[],
            items_checked=sorted(g.get("id", "") for g in ref_groups) if ref_groups else [],
            incomplete=[] if ref_groups else ["reference_groups"],
            rule_id="t1.contamination.reference_group", taxonomy_id="I"))
    elif study_design in _REFERENCE_DESIGNS:
        findings.append(Finding(
            "X", Status.INCOMPLETE, Severity.CRITICAL,
            f"参照設計（study_design={study_design}）の宣言下で reference_groups が未供給",
            "参照/対照/pre-period を持つ設計だが汚染検査の入力が無い＝検査が実行されていない",
            rule_id="t1.contamination.reference_group", taxonomy_id="I"))
        coverage.append(CoverageProof(
            "X", files_read=[], incomplete=["reference_groups"],
            rule_id="t1.contamination.reference_group", taxonomy_id="I"))

    # Y（原稿数値の由来照合）: 掲載された数値が results に遡れるか。プレースホルダ・レンダを
    # 経ない手書き数値（Table 4 脚注の stale な交互作用 p 値 0.64/0.42 等）は、既存の数値照合が
    # 「原稿側に results に無い数値が紛れ込む」向きを見ないため素通りしていた。
    # fail-closed tripwire（Fable 指摘 C-1）: 原稿の存在は section_texts の供給で機械的に判る。
    # 原稿があるのに数値由来照合の入力が無ければ CRITICAL INCOMPLETE（手書き数値のサイレント
    # PASS を、宣言ではなく「原稿があるという事実」からコードで required 化する）。
    reported_nums = inference.get("reported_numbers")
    results_vals = inference.get("results_values")
    if reported_nums is not None or results_vals is not None:
        findings += check_y_number_provenance(reported_nums, results_vals)
        coverage.append(CoverageProof(
            "Y", files_read=[],
            items_checked=[r.get("location", "") for r in reported_nums] if reported_nums else [],
            incomplete=[] if (reported_nums and results_vals is not None)
            else ["reported_numbers_or_results_values"],
            rule_id="t1.manuscript.number_provenance", taxonomy_id="C"))
    elif section_texts is not None:
        findings.append(Finding(
            "Y", Status.INCOMPLETE, Severity.CRITICAL,
            "原稿（section_texts 供給）が存在するのに数値由来照合の入力が未供給",
            "reported_numbers / results_values が無い＝掲載数値の由来照合が実行されていない",
            rule_id="t1.manuscript.number_provenance", taxonomy_id="C"))
        coverage.append(CoverageProof(
            "Y", files_read=[], incomplete=["reported_numbers_or_results_values"],
            rule_id="t1.manuscript.number_provenance", taxonomy_id="C"))

    # S（文体サーフェシング, MINOR・非ブロック）: 明示供給時のみ実行。
    if style_sections is not None:
        findings += check_s_style(style_sections)
        coverage.append(CoverageProof(
            "S", files_read=[],
            items_checked=sorted(style_sections) if style_sections else [],
            incomplete=[] if style_sections else ["style_sections"],
            rule_id="t1.style.ai_phrases", taxonomy_id="G"))


def _critical_fail(findings: list) -> bool:
    return any(
        f.severity is Severity.CRITICAL and f.status in (Status.FAIL, Status.INCOMPLETE)
        for f in findings
    )


def run_tier1(codebook_path: str, dict_csv_path: str,
              methods_claims_path: str, code_filters_path: str,
              outlier_observed: dict | None = None, outlier_ranges: dict | None = None,
              flow: dict | None = None, claimed_ns: dict | None = None,
              bibliography: list | None = None, citation_fetcher=None,
              labels_by_wave: dict | None = None,
              impossible_ranges: dict | None = None,
              censored_by_column: dict | None = None,
              censored_declared_handled: set | None = None,
              immortal_subjects: list | None = None,
              immortal_exposure_type: str | None = None,
              missing_rates: dict | None = None,
              missingness_reported: set | None = None,
              declared_units: dict | None = None,
              observed_unit_center: dict | None = None,
              unit_plausible: dict | None = None,
              bibliography_metadata: list | None = None,
              metadata_fetcher=None,
              labels_by_source: dict | None = None,
              section_texts: dict | None = None,
              study_design: str | None = None,
              sample_type: str | None = None,
              limitations_text: str | None = None,
              inference: dict | None = None,
              style_sections: dict | None = None) -> dict:
    variables = load_codebook(codebook_path)
    with open(methods_claims_path, encoding="utf-8") as fh:
        methods_claims = json.load(fh)
    with open(code_filters_path, encoding="utf-8") as fh:
        code_filters = json.load(fh)

    findings = []
    findings += check_a(variables, dict_csv_path)
    findings += check_b(methods_claims, code_filters)

    checked_a = sorted(v.name for v in variables if v.numeric_map)
    incomplete_a = sorted(v.name for v in variables if not v.numeric_map)

    coverage = [
        CoverageProof(
            "A",
            files_read=[(codebook_path, _sha256(codebook_path)), (dict_csv_path, _sha256(dict_csv_path))],
            items_checked=checked_a,
            incomplete=incomplete_a,
        ),
        CoverageProof(
            "B",
            files_read=[(methods_claims_path, _sha256(methods_claims_path)),
                        (code_filters_path, _sha256(code_filters_path))],
            items_checked=[c["procedure"] for c in methods_claims],
        ),
    ]

    _run_optional_checks(findings, coverage,
                         outlier_observed, outlier_ranges, flow, claimed_ns,
                         bibliography, citation_fetcher, labels_by_wave,
                         impossible_ranges,
                         censored_by_column, censored_declared_handled,
                         immortal_subjects, immortal_exposure_type,
                         missing_rates, missingness_reported,
                         declared_units, observed_unit_center, unit_plausible,
                         bibliography_metadata, metadata_fetcher,
                         labels_by_source,
                         section_texts, study_design,
                         sample_type, limitations_text)

    _run_inference_checks(findings, coverage, inference, style_sections,
                          study_design=study_design, section_texts=section_texts)

    return {"findings": findings, "coverage": coverage, "critical_fail": _critical_fail(findings)}


def run_tier1_generic(codebook_path: str, data_csv_path: str,
                      methods_claims_path: str, code_filters_path: str,
                      user_dictionary_path: str | None = None,
                      data_profile: dict | None = None,
                      outlier_observed: dict | None = None, outlier_ranges: dict | None = None,
                      flow: dict | None = None, claimed_ns: dict | None = None,
                      bibliography: list | None = None, citation_fetcher=None,
                      labels_by_wave: dict | None = None,
                      impossible_ranges: dict | None = None,
                      censored_by_column: dict | None = None,
                      censored_declared_handled: set | None = None,
                      immortal_subjects: list | None = None,
                      immortal_exposure_type: str | None = None,
                      missing_rates: dict | None = None,
                      missingness_reported: set | None = None,
                      declared_units: dict | None = None,
                      observed_unit_center: dict | None = None,
                      unit_plausible: dict | None = None,
                      bibliography_metadata: list | None = None,
                      metadata_fetcher=None,
                      labels_by_source: dict | None = None,
                      section_texts: dict | None = None,
                      study_design: str | None = None,
                      sample_type: str | None = None,
                      limitations_text: str | None = None,
                      inference: dict | None = None,
                      style_sections: dict | None = None) -> dict:
    """generic（臨床）プロファイル版 Tier1 エントリポイント。

    既存 `run_tier1`（jastis: 設問票照合）と並置。一次ソースは生データ CSV の
    自動プロファイル（`pipeline.profile_data.profile_csv`）＋任意ユーザー辞書。
    Finding/CoverageProof/critical_fail の契約は run_tier1 と同一。
    """
    from pipeline.profile_data import profile_csv

    variables = load_generic_codebook(codebook_path)
    if data_profile is None:
        data_profile = profile_csv(data_csv_path)
    user_dictionary = None
    if user_dictionary_path is not None:
        with open(user_dictionary_path, encoding="utf-8") as fh:
            user_dictionary = json.load(fh)
    with open(methods_claims_path, encoding="utf-8") as fh:
        methods_claims = json.load(fh)
    with open(code_filters_path, encoding="utf-8") as fh:
        code_filters = json.load(fh)

    findings = []
    findings += check_a_generic(variables, data_profile, user_dictionary)
    findings += check_b(methods_claims, code_filters)

    files_read_a = [(codebook_path, _sha256(codebook_path)), (data_csv_path, _sha256(data_csv_path))]
    if user_dictionary_path is not None:
        files_read_a.append((user_dictionary_path, _sha256(user_dictionary_path)))
    audited = {f.variable for f in findings if f.check_id == "A" and f.status is not Status.INCOMPLETE}
    coverage = [
        CoverageProof(
            "A",
            files_read=files_read_a,
            items_checked=sorted(v.name for v in variables if v.name in audited),
            incomplete=sorted(v.name for v in variables if v.name not in audited),
        ),
        CoverageProof(
            "B",
            files_read=[(methods_claims_path, _sha256(methods_claims_path)),
                        (code_filters_path, _sha256(code_filters_path))],
            items_checked=[c["procedure"] for c in methods_claims],
        ),
    ]

    _run_optional_checks(findings, coverage,
                         outlier_observed, outlier_ranges, flow, claimed_ns,
                         bibliography, citation_fetcher, labels_by_wave,
                         impossible_ranges,
                         censored_by_column, censored_declared_handled,
                         immortal_subjects, immortal_exposure_type,
                         missing_rates, missingness_reported,
                         declared_units, observed_unit_center, unit_plausible,
                         bibliography_metadata, metadata_fetcher,
                         labels_by_source,
                         section_texts, study_design,
                         sample_type, limitations_text)

    _run_inference_checks(findings, coverage, inference, style_sections,
                          study_design=study_design, section_texts=section_texts)

    return {"findings": findings, "coverage": coverage, "critical_fail": _critical_fail(findings)}
