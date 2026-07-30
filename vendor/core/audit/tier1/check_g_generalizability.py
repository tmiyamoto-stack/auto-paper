"""Check G（一般化可能性スタンス＝限界セクションのセミ決定的サーフェシング）。

非確率／便宜／単施設／臨床レジストリ標本のように母集団代表性を持たない標本で、
限界（Limitations）セクションに一般化可能性・選択バイアス・代表性・外的妥当性の
言及が一切無い場合、それを MAJOR FAIL として**人間・Tier2/3 判定者に surface する**。
非確率パネルの学術的スタンス（限界開示の誠実さ・estimand と対象集団の一致）の
最終判断は LLM 定性判断＝Tier2/3 の管轄であり、本チェックは「限界の言及欠落」を
決定的に洗い出す surfacing に留まる（MAJOR＝ハードブロックしない）。

Finding 契約は check_o/check_l と共有（check_id="G", MAJOR）。決定的・sorted 出力。
"""
from __future__ import annotations

from .findings import Finding, Status, Severity

# 母集団代表性を持たない標本タイプ（一般化言及を要求する対象）。
NON_REPRESENTATIVE = {
    "non_probability", "convenience", "single_center", "clinical_registry",
}

# 限界セクションに一般化可能性への言及があると見なすマーカー（substring・大小非依存）。
# 注意: 「限界」の語そのものはマーカーに含めない。Limitations セクションは常に「限界」を
# 含むため、それを合格条件にすると「測定誤差の限界」だけで一般化への言及なしに PASS して
# しまう（偽陰性）。一般化・代表性・選択バイアス・外的妥当性への実質的言及のみを合格とする。
GENERALIZABILITY_MARKERS = {
    "generaliz", "external validity", "representative", "selection",
    "一般化", "外的妥当性", "代表性", "選択バイアス", "選択的",
}


def check_g_generalizability(sample_type: str,
                             limitations_text: str | None) -> list[Finding]:
    if limitations_text is None:
        return [Finding("G", Status.INCOMPLETE, Severity.MAJOR,
            "限界セクション本文なしで一般化可能性スタンスを照合不能",
            f"limitations_text=None (sample_type={sample_type!r})")]

    if sample_type in NON_REPRESENTATIVE:
        low = limitations_text.lower()
        present = sorted({m for m in GENERALIZABILITY_MARKERS if m.lower() in low})
        if present:
            return [Finding("G", Status.PASS, Severity.MAJOR,
                "非確率/単施設標本だが限界に一般化可能性/選択バイアスの言及あり",
                f"検出マーカー={present} (sample_type={sample_type})")]
        return [Finding("G", Status.FAIL, Severity.MAJOR,
            "非確率/単施設標本だが限界に一般化可能性/選択バイアスの言及なし",
            f"一般化マーカー未検出 (sample_type={sample_type})。"
            "estimand と対象集団の一致・選択バイアスの方向を Tier2/3 判定+人間確認へ")]

    # 母集団/確率標本等は一般化言及を必須としない。
    return [Finding("G", Status.PASS, Severity.MAJOR,
        "母集団/確率標本: 一般化可能性の明示言及は必須ではない",
        f"sample_type={sample_type}")]
