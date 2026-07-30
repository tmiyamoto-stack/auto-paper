"""Tier1 チェックレジストリ（チェック集合の単一の真実）。

## なぜ必要か

「13チェック」と書いた文書と「12個」しか列挙していない構造説明が併存した（共同研究者
レビュー指摘1）。真因は個数の書き間違いではなく、**「何を1チェックと数えるか」の定義が
存在しなかった**ことである。現に同じ実装を3通りに数えられる:

- `check_*.py` モジュール数 = 13
- `check_*` 関数数 = 14（`check_a` / `check_a_generic`、`check_m` / `check_m_metadata`）
- distinct `check_id` = 12（A/B/D/E/G/I/J/K/L/M/O/U）

本モジュールは**規則（rule）を数える単位**と定め、`RULES` を単一の真実にする。文書側の
個数記載はレジストリと lint（`pipeline/lint_registry.py`）で突合されるため、以後ズレたら
テストが落ちる。手書きの個数はどこにも置かない。

## 「監査済み件数」の誇張防止（Codex Sol 指摘）

登録数をそのまま「N件監査した」と表示してはならない。`runner` は check A/B 以外を
**入力が供給されたときだけ**実行するため、A/B しか走らなかった run も登録数で報告すると
完査に見えてしまう。よって件数は4つに分離する（`audit_counts`）:

- **available**: そのプロファイルで利用可能な規則数（レジストリ由来）
- **required**: この run で実行が要求される規則数（always_on ＋ 宣言された feature に対応する規則）
- **executed**: 実際に coverage proof が出た規則数
- **complete**: executed かつ INCOMPLETE を含まない規則数

`required > executed` は**カバレッジの穴**であり、否定エージェントの最優先攻撃対象になる。

## check_id / rule_id / taxonomy_id の三層（名前空間衝突の解消）

実装の一文字 `check_id` と DESIGN §4.2 のタクソノミー A〜N は、同じ文字が別の意味に
使われてドリフトしていた（実装 E=欠測率報告 / G=一般化可能性 / I=不死時間 / L=打ち切り に対し、
タクソノミー E=統計・疫学妥当性 / G=AI文体 / I=時間構造 / L=統計実装詳細）。さらに O/U は
タクソノミー外だった。

一文字 ID の**付け替えは行わない**（findings・coverage proof・回帰テストに焼き付いており、
付け替えは沈黙の破壊リスクが最大で、しかも将来また衝突する）。代わりに:

- `rule_id`（`t1.<領域>.<規則>`）を主キーとする。衝突しない。
- `check_id` は既存の一文字 ID を**凍結**して後方互換に使う（出力に併記）。
- `taxonomy_id` は DESIGN §4.2 の概念分類への写像を明示する。複数規則が同じ
  taxonomy_id を共有してよい（分類なので当然）。

これで「同じ文字が別物を指す」という衝突クラス自体が消える。
"""
from __future__ import annotations

from dataclasses import dataclass

from .findings import Severity


@dataclass(frozen=True)
class CheckRule:
    """Tier1 の1規則。数える単位はこれ。"""

    rule_id: str
    check_id: str          # 凍結された既存の一文字 ID（後方互換）
    taxonomy_id: str       # DESIGN §4.2 の概念分類（A〜N）
    title: str
    module: str
    mode: str              # "deterministic" | "surfacing"
    severity: Severity
    feature: str | None    # 実行を要求する run の特徴（None = always_on）
    profiles: tuple[str, ...]
    requires: tuple[str, ...]   # 供給されないと実行できない runner 引数

    @property
    def always_on(self) -> bool:
        return self.feature is None


# mode の意味（SKILL.md §0 の正直な開示と一致させること）:
#   deterministic — 算術・文字列照合・宣言↔実装の突合で機械的に真偽が決まる。
#   surfacing     — 機械的に「材料」を洗い出すだけ。最終判定は Tier2/3 と人間。
#                   surfacing 規則は critical_fail をトリップさせない（MAJOR/MINOR）。
RULES: tuple[CheckRule, ...] = (
    CheckRule("t1.coding.survey_labels", "A", "A",
              "変数コーディング↔設問票ラベル照合", "check_a_coding",
              "deterministic", Severity.CRITICAL, None, ("jastis",),
              ("codebook_path", "dict_csv_path")),
    CheckRule("t1.coding.data_profile", "A", "A",
              "変数コーディング↔データプロファイル照合", "check_a_generic",
              "deterministic", Severity.CRITICAL, None, ("generic",),
              ("codebook_path", "data_csv_path")),
    CheckRule("t1.methods_code.correspondence", "B", "B",
              "Methods 記載↔コード実装の双方向突合", "check_b_methods_code",
              "deterministic", Severity.CRITICAL, None, ("jastis", "generic"),
              ("methods_claims_path", "code_filters_path")),
    CheckRule("t1.outliers.range", "D", "D",
              "外れ値・生理的不可能値", "check_d_outliers",
              "deterministic", Severity.CRITICAL, "outliers", ("jastis", "generic"),
              ("outlier_observed", "outlier_ranges")),
    CheckRule("t1.flow.n_chain", "K", "K",
              "除外フロー N 連鎖↔記載照合", "check_k_flow",
              "deterministic", Severity.MAJOR, "flow", ("jastis", "generic"),
              ("flow",)),
    CheckRule("t1.citations.existence", "M", "M",
              "引用の DOI/PMID 実在確認", "check_m_citations",
              "deterministic", Severity.CRITICAL, "citations", ("jastis", "generic"),
              ("bibliography", "citation_fetcher")),
    CheckRule("t1.citations.metadata", "M", "M",
              "引用メタデータ（title/authors/year）一致", "check_m_citations",
              "deterministic", Severity.CRITICAL, "citations", ("jastis", "generic"),
              ("bibliography_metadata", "metadata_fetcher")),
    CheckRule("t1.harmonization.labels", "J", "J",
              "波/ソース間ラベル・ハーモナイゼーション", "check_j_harmonization",
              "deterministic", Severity.CRITICAL, "multi_source", ("jastis", "generic"),
              ("labels_by_wave",)),
    CheckRule("t1.censoring.declared", "L", "L",
              "打ち切り値/検出限界の宣言↔出現照合", "check_l_censored",
              "deterministic", Severity.CRITICAL, "censoring", ("jastis", "generic"),
              ("censored_by_column",)),
    CheckRule("t1.immortal_time.window", "I", "I",
              "不死時間バイアス（曝露定義↔追跡開始）", "check_i_immortal",
              "deterministic", Severity.CRITICAL, "time_to_event", ("jastis", "generic"),
              ("immortal_subjects",)),
    CheckRule("t1.missingness.reporting", "E", "E",
              "欠測率↔Methods 報告の照合", "check_e_missingness",
              "deterministic", Severity.MAJOR, "missingness", ("jastis", "generic"),
              ("missing_rates",)),
    CheckRule("t1.missingness.mechanism_implementation", "E", "E",
              "欠測メカニズム宣言↔実装手法の突合", "check_e_mechanism",
              "deterministic", Severity.MAJOR, "missingness", ("jastis", "generic"),
              ("missingness_declared", "missingness_handling")),
    CheckRule("t1.units.consistency", "U", "L",
              "単位混在（mg/dL↔mmol/L 等）", "check_u_units",
              "deterministic", Severity.MAJOR, "units", ("jastis", "generic"),
              ("declared_units",)),
    CheckRule("t1.weights.arithmetic", "W", "L",
              "IPW 重みの算術健全性・宣言↔実装突合", "check_w_weights",
              "deterministic", Severity.CRITICAL, "weighting", ("jastis", "generic"),
              ("ipw_weights",)),
    CheckRule("t1.weights.distribution", "W", "H",
              "IPW 重み分布・有効サンプルサイズ(ESS)の surfacing", "check_w_weights",
              "surfacing", Severity.MAJOR, "weighting", ("jastis", "generic"),
              ("ipw_weights",)),
    CheckRule("t1.attrition.differential", "H", "H",
              "パネル脱落の差分（標準化差の再計算）", "check_h_attrition",
              "surfacing", Severity.MAJOR, "panel", ("jastis", "generic"),
              ("attrition_baseline",)),
    CheckRule("t1.overstatement.causal_language", "O", "E",
              "解釈の誇張（因果含意語）の surfacing", "check_o_overstatement",
              "surfacing", Severity.MAJOR, "manuscript", ("jastis", "generic"),
              ("study_design", "section_texts")),
    CheckRule("t1.generalizability.limitations", "G", "H",
              "一般化可能性スタンスの surfacing", "check_g_generalizability",
              "surfacing", Severity.MAJOR, "manuscript", ("jastis", "generic"),
              ("sample_type", "limitations_text")),
    CheckRule("t1.missingness.declared_vs_implemented", "E", "E",
              "SAP宣言の欠測処理手法↔実行traceの文字通りの突合", "check_e_mechanism",
              "deterministic", Severity.CRITICAL, "missingness", ("jastis", "generic"),
              ("missingness_declared_handling", "missingness_implemented_handling")),
    CheckRule("t1.cluster.model_frame_integrity", "T", "L",
              "クラスタSE宣言↔model frameの整合", "check_t_cluster",
              "deterministic", Severity.CRITICAL, "clustered_se", ("jastis", "generic"),
              ("cluster_ids",)),
    CheckRule("t1.cluster.finite_sample_risk", "T", "L",
              "独立クラスタ数と有限標本補正の要否 surfacing", "check_t_cluster",
              "surfacing", Severity.MAJOR, "clustered_se", ("jastis", "generic"),
              ("cluster_ids",)),
    CheckRule("t1.prereg.analysis_set", "P", "B",
              "事前登録マニフェスト↔実行traceの集合突合（SAPハッシュ凍結込み）",
              "check_p_prereg",
              "deterministic", Severity.CRITICAL, "preregistration", ("jastis", "generic"),
              ("sap_analyses", "executed_analyses")),
    CheckRule("t1.prereg.multiplicity", "P", "B",
              "宣言補正法による補正p値の再計算照合", "check_p_prereg",
              "deterministic", Severity.MAJOR, "preregistration", ("jastis", "generic"),
              ("sap_analyses", "executed_analyses")),
    CheckRule("t1.model.estimability", "Q", "L",
              "掲載係数の推定可能性・宣言共変量の実推定", "check_q_model",
              "deterministic", Severity.CRITICAL, "regression", ("jastis", "generic"),
              ("model_trace",)),
    CheckRule("t1.model.convergence", "Q", "L",
              "収束・完全分離フラグの surfacing", "check_q_model",
              "surfacing", Severity.MAJOR, "regression", ("jastis", "generic"),
              ("model_trace",)),
    CheckRule("t1.model.diagnostics_declared", "Q", "L",
              "SAP宣言診断の実行照合・QIC argmin突合", "check_q_model",
              "deterministic", Severity.MAJOR, "regression", ("jastis", "generic"),
              ("model_trace", "declared_diagnostics")),
    CheckRule("t1.model.spec_correspondence", "R", "B",
              "Methods記載の推定式（回帰変数・固定効果集合）↔コード実装の突合",
              "check_r_model_spec",
              "deterministic", Severity.CRITICAL, "regression", ("jastis", "generic"),
              ("model_specs", "model_implementations")),
    CheckRule("t1.style.ai_phrases", "S", "G",
              "AI 定型表現の所在 surfacing（文体改善候補）", "check_s_style",
              "surfacing", Severity.MINOR, "manuscript", ("jastis", "generic"),
              ("section_texts",)),
    CheckRule("t1.contamination.reference_group", "X", "I",
              "参照/対照群の汚染（非曝露参照・pre-period に曝露済みが混入）",
              "check_x_reference_contamination",
              "deterministic", Severity.CRITICAL, "reference_design", ("jastis", "generic"),
              ("reference_groups",)),
    CheckRule("t1.manuscript.number_provenance", "Y", "C",
              "原稿掲載数値の由来照合（results に遡れない手書き/stale の検出）",
              "check_y_number_provenance",
              "deterministic", Severity.CRITICAL, "manuscript", ("jastis", "generic"),
              ("reported_numbers", "results_values")),
)


def rules_for_profile(profile: str) -> list[CheckRule]:
    """当該プロファイルで利用可能な規則（rule_id 昇順で決定的）。"""
    return sorted((r for r in RULES if profile in r.profiles), key=lambda r: r.rule_id)


def required_rules(profile: str, declared_features: set[str] | None) -> list[CheckRule]:
    """この run で実行が要求される規則。

    always_on 規則＋SAP/設計が宣言した feature に対応する規則。`declared_features`
    が None のときは always_on のみ（feature 宣言が無いのに feature 規則を required に
    数えると、横断研究の run で panel 規則が永久に未達になる）。
    """
    feats = declared_features or set()
    return [r for r in rules_for_profile(profile)
            if r.always_on or (r.feature in feats)]


def audit_counts(profile: str, declared_features: set[str] | None,
                 coverage, findings) -> dict:
    """available/required/executed/complete の4件数（誇張防止・Codex Sol 指摘）。

    coverage/findings は `CoverageProof` / `Finding` のリスト。`rule_id` が設定されて
    いればそれで、無ければ `check_id` で規則に対応づける（後方互換）。
    """
    available = rules_for_profile(profile)
    required = required_rules(profile, declared_features)

    covered_rule_ids = {c.rule_id for c in coverage if getattr(c, "rule_id", None)}
    covered_check_ids = {c.check_id for c in coverage}

    def _executed(rule: CheckRule) -> bool:
        return rule.rule_id in covered_rule_ids or rule.check_id in covered_check_ids

    incomplete_rule_ids = {getattr(f, "rule_id", None) for f in findings
                           if f.status.value == "incomplete"}
    incomplete_check_ids = {f.check_id for f in findings if f.status.value == "incomplete"}
    for c in coverage:
        if c.incomplete:
            incomplete_check_ids.add(c.check_id)
            if getattr(c, "rule_id", None):
                incomplete_rule_ids.add(c.rule_id)

    def _complete(rule: CheckRule) -> bool:
        if not _executed(rule):
            return False
        return not (rule.rule_id in incomplete_rule_ids
                    or rule.check_id in incomplete_check_ids)

    executed = [r for r in available if _executed(r)]
    complete = [r for r in available if _complete(r)]
    unmet = [r.rule_id for r in required if not _executed(r)]

    return {
        "available": len(available),
        "required": len(required),
        "executed": len(executed),
        "complete": len(complete),
        "unmet_required": sorted(unmet),
    }


def rule_ids() -> list[str]:
    return sorted(r.rule_id for r in RULES)


def check_ids() -> list[str]:
    """distinct な一文字 check_id（後方互換の集合）。"""
    return sorted({r.check_id for r in RULES})


def validate_registry() -> list[str]:
    """レジストリ自体の健全性（lint から呼ばれる）。空リスト = 合格。"""
    errors: list[str] = []
    seen: set[str] = set()
    for r in RULES:
        if r.rule_id in seen:
            errors.append(f"duplicate rule_id: {r.rule_id}")
        seen.add(r.rule_id)
        if r.mode not in ("deterministic", "surfacing"):
            errors.append(f"{r.rule_id}: unknown mode '{r.mode}'")
        if r.mode == "surfacing" and r.severity is Severity.CRITICAL:
            errors.append(
                f"{r.rule_id}: surfacing 規則が CRITICAL（surfacing は "
                "critical_fail をトリップしてはならない）")
        if not r.profiles:
            errors.append(f"{r.rule_id}: profiles が空")
    return errors
