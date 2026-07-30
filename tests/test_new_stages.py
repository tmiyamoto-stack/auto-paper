# -*- coding: utf-8 -*-
"""工程4c(英文校閲検証) / 3b(文献配線) / 5b(Tier2/3自動起動) の検証。"""
import json
import os
import subprocess
import sys

import pytest

import check_citations as cc
import check_copyedit as ce
import run_tier23 as t23
from conftest import core_available

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(script, *args):
    p = subprocess.run([sys.executable, os.path.join(SKILL, script), *args],
                       capture_output=True, text=True, cwd=SKILL)
    return p.returncode, p.stdout + p.stderr


# --- 工程4c: 英文校閲が数値を壊していないか ---------------------------------

BEFORE = ("## Results\nThe adjusted OR was 1.62 (95% CI 1.44-1.82) among 11,533 "
          "person-years [1].\n\n## References\n1. X. doi:10.1111/add.70257\n")


def test_prose_only_edit_passes():
    after = BEFORE.replace("The adjusted OR was", "The adjusted odds ratio was")
    assert ce.compare(BEFORE, after) == []


def test_changed_number_is_caught():
    after = BEFORE.replace("1.62", "1.63")
    problems = ce.compare(BEFORE, after)
    assert problems and "数値" in problems[0]


def test_changed_citation_marker_is_caught():
    after = BEFORE.replace("[1]", "[2]")
    assert any("引用マーカー" in p for p in ce.compare(BEFORE, after))


def test_changed_heading_is_caught():
    after = BEFORE.replace("## Results", "## Findings")
    assert any("見出し" in p for p in ce.compare(BEFORE, after))


def test_changed_doi_is_caught():
    after = BEFORE.replace("10.1111/add.70257", "10.1111/add.99999")
    assert any("DOI" in p for p in ce.compare(BEFORE, after))


def test_reintroduced_placeholder_is_caught():
    after = BEFORE.replace("1.62", "{{m1.or}}")
    assert any("プレースホルダ" in p for p in ce.compare(BEFORE, after))


def test_copyedit_cli_exit_codes(tmp_path):
    b, a = tmp_path / "b.md", tmp_path / "a.md"
    b.write_text(BEFORE, encoding="utf-8")
    a.write_text(BEFORE.replace("OR was", "odds ratio was"), encoding="utf-8")
    assert _run("check_copyedit.py", "--before", str(b), "--after", str(a))[0] == 0
    a.write_text(BEFORE.replace("1.62", "9.99"), encoding="utf-8")
    assert _run("check_copyedit.py", "--before", str(b), "--after", str(a))[0] == 1
    assert _run("check_copyedit.py", "--before", str(b), "--after", str(tmp_path / "nope"))[0] == 2


# --- 工程3b: 引用と bibliography の配線 --------------------------------------

def test_citation_wiring_ok():
    man = "A [1] and [2,3].\n\n## References\n1. a\n"
    bib = [{"n": 1, "doi": "10.1/a"}, {"n": 2, "doi": "10.1/b"}, {"n": 3, "pmid": "1"}]
    assert cc.check(man, bib) == []


def test_hallucinated_citation_is_caught():
    man = "A [1] and [7].\n\n## References\n1. a\n"
    bib = [{"n": 1, "doi": "10.1/a"}]
    problems = cc.check(man, bib)
    assert any("[7]" in p and "登録が無い" in p for p in problems)


def test_uncited_bibliography_entry_is_caught():
    man = "A [1].\n\n## References\n1. a\n"
    bib = [{"n": 1, "doi": "10.1/a"}, {"n": 2, "doi": "10.1/b"}]
    assert any("一度も引かれていない" in p for p in cc.check(man, bib))


def test_missing_identifier_is_caught():
    man = "A [1].\n"
    bib = [{"n": 1, "title": "No identifier here"}]
    assert any("識別子" in p for p in cc.check(man, bib))


def test_citation_range_expansion():
    assert cc.cited_numbers("see [2-4] and [7]") == {2, 3, 4, 7}


def test_references_section_not_counted_as_citation():
    """参考文献リスト内の '1.' を引用マーカーと誤認しないこと。"""
    man = "Body cites [1].\n\n## References\n1. A [99] in title\n"
    assert cc.cited_numbers(man) == {1}


def test_citations_cli_missing_bib_is_exit_2(tmp_path):
    d = tmp_path / "run"
    (d / "04_manuscript").mkdir(parents=True)
    (d / "04_manuscript" / "manuscript_v1_en.md").write_text("x [1]\n", encoding="utf-8")
    rc, out = _run("check_citations.py", "--run-dir", str(d))
    assert rc == 2 and "bibliography" in out


# --- 工程5b: Tier2/3 の COI 選定と fail-closed --------------------------------

def test_build_command_known_and_unknown():
    assert t23.build_command("codex", "p")[0] == "codex"
    assert t23.build_command("gemini", "p")[0] == "gemini"
    assert t23.build_command("fable", "p") is None, "CLI を持たないモデルに command を作ってはいけない"


@pytest.mark.skipif(not core_available(), reason="コア未解決")
def test_coi_excludes_generator_family():
    """生成に使った系列が監査者から除外されること（Fable は Claude 系列）。"""
    import core
    core.ensure_core_importable()
    from audit.external.matrix import select_auditors
    cfg = core.load_config()["models"]
    claude_gen = select_auditors("claude", cfg)
    assert "fable" not in claude_gen, "Claude 生成物の監査に Fable が入っている（COI 違反）"
    assert "codex" in claude_gen
    codex_gen = select_auditors("codex", cfg)
    assert "codex" not in codex_gen, "codex 生成物の監査に codex が入っている（COI 違反）"


def test_tier23_missing_findings_is_exit_2(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    rc, out = _run("run_tier23.py", "--run-dir", str(d), "--findings", str(tmp_path / "nope.json"))
    assert rc == 2 and "findings" in out


def test_tier23_bad_inject_spec_is_exit_2(tmp_path):
    d = tmp_path / "run"
    (d / "03_results").mkdir(parents=True)
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"findings": []}), encoding="utf-8")
    rc, out = _run("run_tier23.py", "--run-dir", str(d), "--findings", str(f),
                   "--inject", "fable=/nonexistent.json")
    assert rc == 2


@pytest.mark.skipif(not core_available(), reason="コア未解決")
def test_tier23_dry_run_reports_selection(tmp_path):
    d = tmp_path / "run"
    (d / "03_results").mkdir(parents=True)
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"findings": [
        {"check_id": "A", "status": "fail", "severity": "critical",
         "summary": "s", "evidence": "e", "variable": "v"}]}), encoding="utf-8")
    rc, out = _run("run_tier23.py", "--run-dir", str(d), "--findings", str(f), "--dry-run")
    assert rc == 0
    assert "選定された監査者" in out and "Tier2 対象" in out


def test_only_unresolved_findings_go_to_tier2(tmp_path):
    """PASS の finding は Tier2 に回さない（コストと恣意性を避ける）。"""
    d = tmp_path / "run"
    (d / "03_results").mkdir(parents=True)
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"findings": [
        {"check_id": "A", "status": "pass", "severity": "critical", "summary": "ok", "evidence": ""},
        {"check_id": "B", "status": "fail", "severity": "critical", "summary": "ng", "evidence": ""},
        {"check_id": "C", "status": "incomplete", "severity": "major", "summary": "?", "evidence": ""},
    ]}), encoding="utf-8")
    rc, out = _run("run_tier23.py", "--run-dir", str(d), "--findings", str(f), "--dry-run")
    assert "Tier2 対象      : 2 件" in out, out


def test_new_agent_prompts_exist():
    for name in ("03b_literature.md", "04c_copyedit.md"):
        p = os.path.join(SKILL, "agents", name)
        assert os.path.exists(p) and os.path.getsize(p) > 500, f"agents/{name} が無い/薄い"
