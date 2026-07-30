from __future__ import annotations

_REQUIRED = [
    "G0", "G1.5", "G1", "G2",
    "1. 設計", "2. 変数", "3. 分析", "4. 執筆", "5. 監査", "6. 自己修復", "7. 最終判定",
    "入力契約", "出力契約", "統括", "manifest", "INCOMPLETE",
]


def lint_skill(path: str) -> list[str]:
    """Structural linter for SKILL.md: checks that every required orchestrator
    element (gates, stage headings, non-interference contract keywords, manifest
    validation reference, INCOMPLETE-blocks-progression policy) is present.

    Empty list == pass. Substring containment only; does not validate prose quality.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return [f"SKILL.md: missing required element '{tok}'" for tok in _REQUIRED if tok not in text]
