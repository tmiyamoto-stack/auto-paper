from __future__ import annotations

import os

REQUIRED_SECTIONS = ["## 入力契約", "## 出力成果物", "## 手順", "## ゲート", "## モデル"]
KNOWN_ARTIFACTS = {
    "design_protocol.md", "sap.md", "variable_codebook.json", "results.json",
    "flow.json", "methods_claims.json", "code_filters.json", "manuscript.md",
    # generic（臨床）プロファイルの追加成果物
    "data_profile.json", "user_dictionary.json",
}
_AGENT_FILES = ["01_design.md", "02_variables.md", "03_analysis.md", "04_writing.md"]


def lint_agent(path: str) -> list[str]:
    """Structural linter for a single pipeline-stage agent prompt file.

    Checks that all REQUIRED_SECTIONS headings are present and that the
    '## 出力成果物' section names at least one KNOWN_ARTIFACTS entry.
    Empty list == pass. Substring containment only; does not judge prose quality.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    errs = [f"missing section '{s}'" for s in REQUIRED_SECTIONS if s not in text]
    idx = text.find("## 出力成果物")
    if idx != -1:
        nxt = text.find("\n## ", idx + 1)
        section = text[idx: nxt if nxt != -1 else len(text)]
        if not any(a in section for a in KNOWN_ARTIFACTS):
            errs.append("出力成果物 section names no known artifact")
    return errs


def lint_all_agents(agents_dir: str) -> dict[str, list[str]]:
    return {fn: lint_agent(os.path.join(agents_dir, fn)) for fn in _AGENT_FILES}


_AUDIT_SECTIONS = ["## 役割", "## 入力", "## 出力", "## 規則"]
_AUDIT_TOKENS = {
    "05_audit.md": ["Tier1", "Tier2", "Tier3"],
    "negation.md": ["カバレッジ", "反証"],
    "adjudicator.md": ["盲検", "覆せない"],
}


def _lint_audit_file(path: str, name: str) -> list[str]:
    """Structural linter for a single audit-stage agent prompt file
    (05_audit.md / negation.md / adjudicator.md).

    Checks that all _AUDIT_SECTIONS headings are present and that the
    file contains the required tokens for its name (per _AUDIT_TOKENS).
    Empty list == pass. Substring containment only; does not judge prose quality.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    errs = [f"missing section '{s}'" for s in _AUDIT_SECTIONS if s not in text]
    for tok in _AUDIT_TOKENS.get(name, []):
        if tok not in text:
            errs.append(f"missing token '{tok}'")
    return errs


def lint_audit_agents(agents_dir: str) -> dict[str, list[str]]:
    return {name: _lint_audit_file(os.path.join(agents_dir, name), name)
            for name in ("05_audit.md", "negation.md", "adjudicator.md")}


_JUDGMENT_SECTIONS = ["## 役割", "## 判定観点", "## 判定基準", "## 出力"]
_JUDGMENT_FILES = (
    "identification_strategy.md",
    "interpretation.md",
    "generalizability.md",
    # 共同研究者レビューで追加された Tier2 ルーブリック（報告構造5項目・文体・引用整合）。
    "reporting_structure.md",
    "style.md",
    "citation_fit.md",
)


def _lint_judgment_file(path: str) -> list[str]:
    """Structural linter for a single Tier2/3 judge checklist rubric.

    Checks the file exists and contains all _JUDGMENT_SECTIONS headings.
    Substring containment only; does not judge prose quality.
    Empty list == pass.
    """
    if not os.path.exists(path):
        return ["file not found"]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return [f"missing section '{s}'" for s in _JUDGMENT_SECTIONS if s not in text]


def lint_judgment_checklists(checklists_dir: str) -> dict[str, list[str]]:
    """Lint the three Tier2/3 judge checklist rubrics under checklists_dir.

    Returns {filename: [errors]}; each value empty == that file passes.
    """
    return {name: _lint_judgment_file(os.path.join(checklists_dir, name))
            for name in _JUDGMENT_FILES}
