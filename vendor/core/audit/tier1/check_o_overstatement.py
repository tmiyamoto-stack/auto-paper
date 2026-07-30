"""Check O（解釈の誇張＝因果含意表現のセミ決定的サーフェシング）。

観察研究（observational）の Results/Conclusions に因果を含意する語（cause/effect
of/reduces/予防する/引き起こす 等）が現れたら、それを MAJOR FAIL として
**人間・Tier2/3 判定者に surface する**。これは因果の是非を機械が最終判定する
ものではない（因果推論の妥当性は識別戦略に依存し LLM 定性判断＝Tier2/3 の管轄）。
本チェックは「観察研究なのに関連(association)ではなく因果を主張していそうな箇所」
を決定的に洗い出し、判定者が精査する材料を提供するに留まる（MAJOR＝ハードブロック
しない surfacing）。RCT では因果表現は許容され PASS、デザイン未宣言は INCOMPLETE。

Finding 契約は check_d/check_l と共有（check_id="O", MAJOR）。決定的・sorted 出力。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity

# 因果を含意する語（英語＋日本語）。substring・大文字小文字非依存で照合する。
CAUSAL_TERMS = {
    "cause", "causes", "caused", "causal", "effect of", "leads to", "lead to",
    "results in", "reduces", "increases risk", "decreases", "prevents",
    "protects against",
    "因果", "引き起こす", "もたらす", "減少させる", "増加させる", "予防する",
    "効果により", "原因",
}

# 因果含意を精査する原稿セクション（sorted で決定的順序）。
_SCANNED_SECTIONS = ("results", "conclusions")


def check_o_overstatement(section_texts: dict[str, str] | None,
                          study_design: str) -> list[Finding]:
    if section_texts is None:
        return [Finding("O", Status.INCOMPLETE, Severity.MAJOR,
            "原稿本文なしで解釈の誇張を照合不能",
            "section_texts=None")]

    if study_design == "observational":
        findings: list[Finding] = []
        for section in sorted(_SCANNED_SECTIONS):
            text = section_texts.get(section)
            if not text:
                continue
            low = text.lower()
            matched = sorted({t for t in CAUSAL_TERMS if t.lower() in low})
            if matched:
                findings.append(Finding("O", Status.FAIL, Severity.MAJOR,
                    f"観察研究で因果を含意する表現: {matched} in {section}",
                    "関連(association)の語へ緩和し、因果主張は Tier2/3 判定+人間確認へ。"
                    f"該当語={matched} セクション={section}",
                    variable=section))
        if not findings:
            findings.append(Finding("O", Status.PASS, Severity.MAJOR,
                "観察研究の Results/Conclusions に因果含意語なし",
                f"走査セクション={sorted(_SCANNED_SECTIONS)}"))
        return findings

    if study_design == "rct":
        return [Finding("O", Status.PASS, Severity.MAJOR,
            "RCT: 因果表現は許容（フラグなし）",
            "study_design=rct")]

    # "unknown" もしくは想定外のデザイン宣言は判定不能（fail-closed）。
    return [Finding("O", Status.INCOMPLETE, Severity.MAJOR,
        "デザイン未宣言で解釈の誇張を判定不能",
        f"study_design={study_design!r}")]
