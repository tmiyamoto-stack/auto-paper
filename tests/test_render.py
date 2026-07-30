# -*- coding: utf-8 -*-
"""render_manuscript.py（工程4b: 差し込み）の検証。

この工程は従来どこにも配線されておらず、原稿がプレースホルダのままだった。
最重要の性質は fail-closed である: 未解決が1件でもあれば**書き出さない**。
部分的に埋まった原稿が投稿物になるのを防ぐ。
"""
import json
import os
import subprocess
import sys

import pytest

import render_manuscript as rm

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESULTS = {
    "m1": {"or": 1.6162, "ci_low": 1.4387, "ci_high": 1.8157},
    "flow": {"analysis_n": 11533},
    "rows": [{"or": 0.8194}],
}


def _mkrun(tmp_path, body):
    d = tmp_path / "run"
    (d / "03_results").mkdir(parents=True)
    (d / "04_manuscript").mkdir(parents=True)
    (d / "03_results" / "results.json").write_text(json.dumps(RESULTS), encoding="utf-8")
    (d / "04_manuscript" / "manuscript_en.md").write_text(body, encoding="utf-8")
    return d


def _run(run_dir, *extra):
    p = subprocess.run([sys.executable, os.path.join(SKILL, "render_manuscript.py"),
                        "--run-dir", str(run_dir), *extra],
                       capture_output=True, text=True, cwd=SKILL)
    return p.returncode, p.stdout + p.stderr


def test_resolves_dotted_paths_and_format_specs(tmp_path):
    d = _mkrun(tmp_path, "OR {{m1.or:.2f}} CI {{m1.ci_low:.2f}}-{{m1.ci_high:.2f}} "
                         "N {{flow.analysis_n:,}} sec {{rows.0.or:.2f}}\n")
    rc, out = _run(d)
    assert rc == 0, out
    got = (d / "04_manuscript" / "manuscript_v1_en.md").read_text(encoding="utf-8")
    assert "OR 1.62 CI 1.44-1.82 N 11,533 sec 0.82" in got


def test_unresolved_placeholder_writes_nothing(tmp_path):
    """未解決があれば exit 2 かつ**原稿を書き出さない**。"""
    d = _mkrun(tmp_path, "OR {{m1.or:.2f}} and {{nope.missing}}\n")
    rc, out = _run(d)
    assert rc == 2
    assert "nope.missing" in out
    assert not (d / "04_manuscript" / "manuscript_v1_en.md").exists(), \
        "未解決なのに部分的に埋まった原稿が書き出された"


def test_all_unresolved_keys_are_listed(tmp_path):
    d = _mkrun(tmp_path, "{{a.b}} {{c.d}} {{e.f}}\n")
    rc, out = _run(d)
    assert rc == 2
    for k in ("a.b", "c.d", "e.f"):
        assert k in out, f"未解決キー {k} が列挙されていない"


def test_bad_format_spec_is_reported(tmp_path):
    """数値でない値に数値書式を当てたら黙って通さない。"""
    d = _mkrun(tmp_path, "{{rows:.2f}}\n")
    rc, out = _run(d)
    assert rc == 2


def test_missing_results_is_exit_2(tmp_path):
    d = tmp_path / "run"
    (d / "04_manuscript").mkdir(parents=True)
    (d / "04_manuscript" / "manuscript_en.md").write_text("x\n", encoding="utf-8")
    rc, out = _run(d)
    assert rc == 2 and "results.json" in out


def test_word_limit_over_returns_1_but_writes(tmp_path):
    """語数超過は exit 1。原稿は出す（推敲対象として提示するため）。"""
    body = "## Abstract\n" + " ".join(["word"] * 300) + "\n\n## Introduction\nshort\n\n## References\n1. X\n"
    d = _mkrun(tmp_path, body)
    rc, out = _run(d, "--limits", '{"abstract":250}')
    assert rc == 1
    assert "語数超過" in out
    assert (d / "04_manuscript" / "manuscript_v1_en.md").exists()


def test_word_limit_within_returns_0(tmp_path):
    body = "## Abstract\nshort abstract here\n\n## Introduction\nbody\n\n## References\n1. X\n"
    d = _mkrun(tmp_path, body)
    rc, out = _run(d, "--limits", '{"abstract":250,"body":4000}')
    assert rc == 0, out


def test_english_template_exists_and_is_placeholder_only():
    """英語テンプレートが存在し、手書き数値の例を含まないこと。"""
    p = os.path.join(SKILL, "templates", "manuscript_en.md")
    assert os.path.exists(p), "templates/manuscript_en.md が無い"
    s = open(p, encoding="utf-8").read()
    for sec in ("## Abstract", "## Introduction", "## Methods", "## Results",
                "## Discussion", "## References"):
        assert sec in s, f"テンプレートに {sec} が無い"
    assert "{{" in s, "プレースホルダの例が無い"


def test_render_helper_is_pure(tmp_path):
    """render() が (結果, 未解決キー) を返す純関数であること。"""
    out, missing = rm.render("{{m1.or:.2f}} {{zzz}}", RESULTS)
    assert "1.62" in out
    assert missing == ["zzz"]
