# -*- coding: utf-8 -*-
"""プロンプト層の完全性検証。

SKILL.md や 05_audit.md が参照するプロンプト・ルーブリックが実在することを固定する。
初版では「監査系プロンプトはコア側を共有する」と書きながら実際には同梱しておらず、
単体 clone では Tier2/3 の手順書が丸ごと欠落していた（＝Fable/Sol を使う手順が無い）。
参照先の欠落は静かに起きるのでテストで押さえる。
"""
import os
import re

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_AGENTS = [
    "01_design.md", "02_variables.md", "03_analysis.md", "04_writing.md",
    "05_audit.md", "negation.md", "adjudicator.md",
]
REQUIRED_CHECKLISTS = [
    "identification_strategy.md", "interpretation.md", "generalizability.md",
    "reporting_structure.md", "style.md", "citation_fit.md",
]


def test_all_agent_prompts_present():
    for name in REQUIRED_AGENTS:
        p = os.path.join(SKILL, "agents", name)
        assert os.path.exists(p), f"エージェントプロンプトが無い: agents/{name}"
        assert os.path.getsize(p) > 500, f"中身が薄すぎる: agents/{name}"


def test_all_judgment_checklists_present():
    for name in REQUIRED_CHECKLISTS:
        p = os.path.join(SKILL, "references", "judgment_checklists", name)
        assert os.path.exists(p), f"判定ルーブリックが無い: {name}"


def test_style_lexicon_present():
    assert os.path.exists(os.path.join(SKILL, "references", "style_lexicon.md"))


def test_audit_prompt_declares_fable_and_sol_roles():
    """05_audit.md が Fable/Sol の役割と COI 制約を明示していること。"""
    s = open(os.path.join(SKILL, "agents", "05_audit.md"), encoding="utf-8").read()
    assert "audit_critical_primary" in s and "audit_tiebreak" in s
    assert "Sol" in s and "Fable" in s
    assert "select_auditors" in s, "COI 除外の手続きが書かれていない"
    assert "tiebreak" in s, "Fable が第三票であることが書かれていない"


def test_audit_prompt_references_only_existing_files():
    """05_audit.md が参照する references/ のファイルが実在すること。"""
    s = open(os.path.join(SKILL, "agents", "05_audit.md"), encoding="utf-8").read()
    # {a,b,c}.md 展開に対応
    for m in re.finditer(r"references/judgment_checklists/\{([^}]+)\}\.md", s):
        for name in m.group(1).split(","):
            p = os.path.join(SKILL, "references", "judgment_checklists", name.strip() + ".md")
            assert os.path.exists(p), f"参照先が無い: {name}"
    for m in re.finditer(r"`(references/[a-z_/]+\.md)`", s):
        assert os.path.exists(os.path.join(SKILL, m.group(1))), f"参照先が無い: {m.group(1)}"


def test_models_config_matches_audit_prompt():
    """config.yaml の監査ロールと 05_audit.md の記述が食い違わないこと。"""
    import json
    cfg = json.load(open(os.path.join(SKILL, "config.yaml"), encoding="utf-8"))
    models = cfg["models"]
    assert models["audit_critical_primary"] == "codex"
    assert models["audit_tiebreak"] == "fable"
    s = open(os.path.join(SKILL, "agents", "05_audit.md"), encoding="utf-8").read()
    for role, model in (("audit_critical_primary", "codex"),
                        ("audit_critical_secondary", "gemini"),
                        ("audit_tiebreak", "fable")):
        assert f"`{role}: {model}`" in s or f"{role}` | {model}" in s or model in s, \
            f"05_audit.md に {role}={model} の記述が無い"
