"""Check S（AI 定型表現の所在サーフェシング＝文体改善候補の洗い出し）。

共同研究者レビュー指摘(2)。辞書は humanizer_academic（K. Matsui, MIT License,
https://github.com/matsuikentaro1/humanizer_academic）の 34 パターンのうち、
**語彙・記号レベルで決定的に照合できるものだけ**を抜き出してスナップショットした
（`references/style_lexicon.md` に出典と取り込み範囲を記載）。実行時に GitHub を
参照しない（決定性テスト DESIGN §7-3 が壊れるため）。

## このチェックが主張しないこと（両レビューが一致して要求した明示）

1. **AI が書いたことの検出ではない。** 辞書ヒットは AI 生成の証拠ではない。これらの
   語句は非ネイティブ研究者の常用表現と大きく重なる。文体の帰属判定は機械的に証明
   不能であり、本チェックは行わない。
2. **AI 検出器の回避が目的ではない。** 目的は「学術散文としての自然さ・簡潔さ」であり、
   AI 利用の秘匿ではない。検出回避を目的化すると、AI 利用開示を求めるジャーナル方針と
   正面衝突する。
3. **投稿可否ゲートではない。** severity は MINOR、mode は surfacing であり
   `critical_fail` をトリップしない。FAIL の意味は「文体改善候補がここにある」であって
   「欠陥がある」ではない。
4. **書き換えは行わない。** 監査エージェントは原稿を編集できない（SKILL.md §1）。
   修正規則は工程4（執筆）と revision エージェントの管轄。

## 日本語について（Codex Sol の事実指摘）

humanizer_academic は英語医学論文向けであり、公開 SKILL.md に日本語規則は無い。
よって日本語辞書 `_JA_PATTERNS` は**本スキル独自の追加**であり、humanizer 由来ではない。
「humanizer は日英対応」と記載してはならない。

## em dash について（Codex Sol の反例）

humanizer は em dash ゼロ許容だが、"The primary endpoint—death from any cause—…"
のような正当な用法も必ずヒットする。したがって本チェックでは em dash を MINOR の
surfacing に留め、FAIL ではなく**件数の報告**として扱う。
"""
from __future__ import annotations

import re

from .findings import Finding, Status, Severity

_RULE = "t1.style.ai_phrases"

# --- 英語: humanizer_academic 由来（語彙・記号レベルの決定的照合が可能なもののみ） ---
# パターン7「AI vocabulary」のうち、学術文で正当用法が少ない語に絞る。
# "comprehensive"/"key"/"valuable" 等は正当用法が多いため意図的に除外した（偽陽性抑制）。
_EN_VOCAB = (
    "delve", "tapestry", "testament", "pivotal", "multifaceted", "holistic",
    "intricate", "intricacies", "interplay", "showcase", "underscore",
    "underscores", "underscoring", "landscape of", "vibrant", "garner",
    "fostering", "enduring legacy",
)
# パターン8「copula avoidance」。
_EN_COPULA = ("serves as", "stands as", "boasts", "represents a", "marks a")
# パターン9「negative parallelism」。
_EN_NEGPAR = ("not only", "not merely", "it is not just", "rather than merely")
# パターン16「filler phrases」。
_EN_FILLER = (
    "in order to", "due to the fact that", "at the present time",
    "it is important to note that", "has the ability to", "with respect to",
    "it is worth noting that",
)
# パターン19/21/24/25「word choice」。
_EN_WORDCHOICE = ("linked to", "via ", "yield ", "yields ")

_EN_GROUPS = {
    "AI常用語彙": _EN_VOCAB,
    "コピュラ回避": _EN_COPULA,
    "否定並列": _EN_NEGPAR,
    "冗長定型句": _EN_FILLER,
    "語選択": _EN_WORDCHOICE,
}

# --- 日本語: 本スキル独自の追加（humanizer 由来ではない） ---
_JA_PATTERNS = {
    "AI常用語彙": ("重要な示唆", "極めて重要", "多面的", "多岐にわたる",
                   "さらなる検討が待たれる", "今後の展開が期待される"),
    "冗長定型句": ("と言っても過言ではない", "することが可能である",
                   "という点において", "に他ならない"),
    "内容希薄な評価文": ("本研究の意義は大きい", "重要な一歩", "貢献するものである"),
}

# 記号レベル（決定的だが正当用法があるため件数報告に留める）。
_EM_DASH = "—"
_CURLY_QUOTES = ("“", "”", "‘", "’")


def _count_occurrences(text: str, needle: str) -> int:
    return len(re.findall(re.escape(needle), text, flags=re.IGNORECASE))


def check_s_style(section_texts: dict[str, str] | None,
                  max_report_per_group: int = 8) -> list[Finding]:
    """原稿本文から AI 定型表現の所在を決定的に洗い出す（判定はしない）。

    `section_texts`: {セクション名: 本文}。None は INCOMPLETE（サイレント PASS 禁止）。
    """
    if not section_texts:
        return [Finding("S", Status.INCOMPLETE, Severity.MINOR,
            "原稿本文未提供で文体サーフェシング不能",
            "section_texts=None", rule_id=_RULE, taxonomy_id="G")]

    findings: list[Finding] = []

    for section in sorted(section_texts):
        text = section_texts[section] or ""
        if not text:
            findings.append(Finding("S", Status.INCOMPLETE, Severity.MINOR,
                f"本文が空でサーフェシング不能: {section}",
                f"section={section}", variable=section,
                rule_id=_RULE, taxonomy_id="G"))
            continue

        for group, patterns in list(_EN_GROUPS.items()) + list(_JA_PATTERNS.items()):
            hits = []
            for pat in patterns:
                n = _count_occurrences(text, pat)
                if n:
                    hits.append((pat.strip(), n))
            if not hits:
                continue
            hits.sort()
            shown = hits[:max_report_per_group]
            more = len(hits) - len(shown)
            detail = ", ".join(f"{p}×{n}" for p, n in shown)
            if more > 0:
                detail += f", 他{more}種"
            findings.append(Finding("S", Status.FAIL, Severity.MINOR,
                f"文体改善候補（{group}）: {section}",
                f"section={section}, {detail}。"
                "※AI 生成の証拠ではなく、学術散文としての簡潔さを高める候補。"
                "書き換えは revision エージェントが行い、監査は所在提示に留まる",
                variable=section, rule_id=_RULE, taxonomy_id="G"))

        n_dash = text.count(_EM_DASH)
        n_curly = sum(text.count(q) for q in _CURLY_QUOTES)
        if n_dash or n_curly:
            findings.append(Finding("S", Status.PASS, Severity.MINOR,
                f"記号使用の報告（判定なし）: {section}",
                f"section={section}, em dash={n_dash}, curly quote={n_curly}。"
                "※em dash には正当な学術用法があるため FAIL にしない。"
                "投稿先の体裁規定に合わせて執筆側で判断する",
                variable=section, rule_id=_RULE, taxonomy_id="G"))

    return findings
