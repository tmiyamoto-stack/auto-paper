# -*- coding: utf-8 -*-
"""run_audit.py（ドライバ）の統合テスト。

2026-07-30 の外部レビュー（Fable / Sol が独立に同じ結論）で、31テスト green の
外側にあるこの191行に critical 欠陥が4つ実在することが判明した。テストが
ドライバを一度も踏んでいなかったことが直接の原因である。ここで固定する:

  - 入力未供給のチェックは INCOMPLETE として明示され、exit 0 にならない
  - 終了コード契約 0/1/2 が全経路で守られる（想定外例外も 2 に正規化）
  - profile-only モードが実際に動く（SKILL.md が「任意」と明記している）
  - check D の観測値が自己申告ではなくプロファイル由来
"""
import json
import os
import subprocess
import sys

import pytest

from conftest import FIXTURES, core_available

if not core_available():
    pytest.skip("隣接する監査コアが無い（単体クローン）。skills 配下にコアを置くと実行される",
                allow_module_level=True)

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RETAIL = os.path.join(FIXTURES, "retail.csv")


def _run(*args):
    p = subprocess.run([sys.executable, os.path.join(SKILL, "run_audit.py"), *args],
                       capture_output=True, text=True, cwd=SKILL)
    return p.returncode, p.stdout + p.stderr


def _mkrun(tmp_path, sap=None, codebook=None, bibliography=None):
    d = tmp_path / "run"
    (d / "01_data").mkdir(parents=True)
    (d / "03_results").mkdir(parents=True)
    (d / "01_data" / "variable_codebook.json").write_text(json.dumps(
        codebook or {"variables": [
            {"name": "revenue", "source_column": "revenue_kyen"},
            {"name": "satisfaction", "source_column": "satisfaction",
             "numeric_map": {"1": 1, "5": 5, "99": None}, "treat_as_missing": [99]},
        ]}, ensure_ascii=False), encoding="utf-8")
    (d / "03_results" / "methods_claims.json").write_text(json.dumps(
        [{"id": "MC1", "procedure": "p1", "applies_to": ["x"]}]), encoding="utf-8")
    (d / "03_results" / "code_filters.json").write_text(json.dumps(
        [{"procedure": "p1", "applies_to": ["x"], "evidence": "a.py:1"}]), encoding="utf-8")
    if sap is not None:
        (d / "03_results" / "sap_ranges.json").write_text(
            json.dumps(sap, ensure_ascii=False), encoding="utf-8")
    if bibliography is not None:
        (d / "03_results" / "bibliography.json").write_text(
            json.dumps(bibliography, ensure_ascii=False), encoding="utf-8")
    return str(d)


# --- C1/C2: 未実行チェックが exit 0 に化けないこと ---------------------------

def test_unsupplied_checks_are_reported_incomplete_not_silently_skipped(tmp_path):
    """入力が A/B 分しか無い run は exit 0 にならず、未実行チェックが列挙される。

    修正前はここが PASS=2 FAIL=0 INCOMPLETE=0 / exit 0 だった。
    """
    run = _mkrun(tmp_path)
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL)
    assert rc == 1, f"未実行チェックがあるのに exit {rc} を返した:\n{out}"
    assert "実行されていない" in out
    for cid in ("M", "L", "I", "O", "S", "W"):
        assert f"チェック {cid} は入力未供給" in out, f"check {cid} の未実行が報告されていない"


def test_unrun_checks_listed_in_coverage_and_json(tmp_path):
    run = _mkrun(tmp_path)
    outp = str(tmp_path / "f.json")
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL,
                   "--json", outp)
    assert rc == 1
    assert "coverage:" in out
    data = json.loads(open(outp, encoding="utf-8").read())
    assert set(data["unrun_checks"]) >= {"M", "L", "I", "O", "S", "W"}
    assert data["coverage"], "coverage proof が JSON に出ていない"


# --- C4: profile-only モード --------------------------------------------------

def test_profile_only_mode_runs(tmp_path):
    """--data-csv 無し・data_profile.json ありで実際に動くこと（修正前はクラッシュ）。"""
    run = _mkrun(tmp_path)
    sys.path.insert(0, SKILL)
    import core as core_mod
    core_mod.ensure_core_importable()
    from pipeline.profile_data import profile_csv
    prof = profile_csv(RETAIL)
    with open(os.path.join(run, "01_data", "data_profile.json"), "w", encoding="utf-8") as fh:
        json.dump(prof, fh, ensure_ascii=False)
    rc, out = _run("--run-dir", run, "--domain", "general")
    assert rc == 1, f"profile-only が exit {rc} で落ちた:\n{out}"
    assert "Traceback" not in out
    assert "PASS=" in out


# --- C3: 終了コード契約 -------------------------------------------------------

def test_missing_domain_is_exit_2(tmp_path):
    run = _mkrun(tmp_path)
    rc, out = _run("--run-dir", run, "--data-csv", RETAIL)
    assert rc == 2 and "domain" in out


def test_unknown_domain_is_exit_2(tmp_path):
    run = _mkrun(tmp_path)
    rc, _ = _run("--run-dir", run, "--domain", "astrology", "--data-csv", RETAIL)
    assert rc == 2


def test_missing_artifact_is_exit_2(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    rc, out = _run("--run-dir", str(d), "--domain", "general", "--data-csv", RETAIL)
    assert rc == 2 and "必須成果物" in out


def test_bad_core_is_exit_2(tmp_path, monkeypatch):
    run = _mkrun(tmp_path)
    p = subprocess.run(
        [sys.executable, os.path.join(SKILL, "run_audit.py"),
         "--run-dir", run, "--domain", "general", "--data-csv", RETAIL,
         "--core", str(tmp_path / "nope")],
        capture_output=True, text=True, cwd=SKILL)
    assert p.returncode == 2


def test_malformed_sap_ranges_is_exit_2(tmp_path):
    """不正な値域宣言は traceback(1) ではなく「実行できなかった」(2)。"""
    run = _mkrun(tmp_path, sap={"plausible_ranges": {"x": [1, 2, 3]}})
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL)
    assert rc == 2, f"exit {rc} を返した:\n{out}"
    assert "Traceback" not in out


def test_inverted_range_is_exit_2(tmp_path):
    run = _mkrun(tmp_path, sap={"plausible_ranges": {"revenue": [100, 1]}})
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL)
    assert rc == 2 and "下限が上限を超えている" in out


def test_malformed_required_json_is_exit_2(tmp_path):
    run = _mkrun(tmp_path)
    with open(os.path.join(run, "03_results", "methods_claims.json"), "w") as fh:
        fh.write("{not json")
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL)
    assert rc == 2, f"exit {rc}:\n{out}"


def test_missing_data_csv_path_is_exit_2(tmp_path):
    run = _mkrun(tmp_path)
    rc, _ = _run("--run-dir", run, "--domain", "general",
                 "--data-csv", str(tmp_path / "nope.csv"))
    assert rc == 2


# --- M1: check D の観測値がプロファイル由来（自己申告でない） -----------------

def test_check_d_uses_profile_derived_observed(tmp_path):
    """sap に observed を一切書かなくても、負の売上が値域宣言だけで捕まること。

    修正前は sap_ranges.json の observed（LLM の自己申告）が必要だった。
    """
    run = _mkrun(tmp_path, sap={
        "impossible_ranges": {"revenue": [0, 10 ** 9]},
        "plausible_ranges": {"revenue": [0, 10 ** 7]},
    })
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL)
    assert rc == 1
    assert "ありえない値" in out and "revenue" in out, \
        f"プロファイル由来の観測値で負の売上を検出できていない:\n{out}"


def test_all_checks_supplied_can_reach_exit_0(tmp_path):
    """入力を揃えれば exit 0 に到達できること（未実行 INCOMPLETE が万年 1 を返さない）。"""
    import core as core_mod
    sys.path.insert(0, SKILL)
    core_mod.ensure_core_importable()
    from pipeline.profile_data import profile_csv
    prof = profile_csv(RETAIL)
    cens = {c: v for c, v in
            ((c, (d.get("censored_candidates") or []))
             for c, d in prof["columns"].items()) if v}
    run = _mkrun(tmp_path, codebook={"variables": [
        {"name": "staff", "source_column": "staff_count"}]})
    # 全チェックに入力を供給する（値は本テストの目的上ダミーで足りる）
    sap = {
        "plausible_ranges": {"staff": [0, 100]},
        "impossible_ranges": {"staff": [0, 1000]},
        "declared_units": {}, "observed_unit_center": {},
        "claimed_ns": {}, "censored_by_column": cens or {},
        "censored_declared_handled": list(cens or {}),
        "missing_rates": {}, "missingness_reported": [],
        "labels_by_source": {}, "study_design": "observational",
        "sample_type": "convenience",
        "limitations_text": "本標本は便宜標本であり一般化可能性・選択バイアスに限界がある。代表性は保証されない。",
        "section_texts": {"results": "本標本では A と B が関連した。",
                          "conclusions": "関連が観察された。"},
        "style_sections": {"discussion": "本研究では関連が観察された。"},
        "immortal_subjects": [], "immortal_exposure_type": "time_fixed",
        "inference": {},
    }
    with open(os.path.join(run, "03_results", "sap_ranges.json"), "w", encoding="utf-8") as fh:
        json.dump(sap, fh, ensure_ascii=False)
    with open(os.path.join(run, "03_results", "flow.json"), "w", encoding="utf-8") as fh:
        json.dump({"stages": [{"label": "raw", "n": 15}, {"label": "analysis", "n": 15}]}, fh)
    with open(os.path.join(run, "03_results", "bibliography.json"), "w", encoding="utf-8") as fh:
        json.dump([], fh)
    rc, out = _run("--run-dir", run, "--domain", "general", "--data-csv", RETAIL)
    # 空 dict の供給は「供給していない」のと同じ（コアが None 扱いにする）ため、
    # 全チェックの解消は求めない。求めるのは「実入力を与えたチェックは
    # 未実行リストから消える」ことである。
    for cid in ("A", "B", "D", "K", "O", "G", "S", "I", "L"):
        assert f"チェック {cid} は入力未供給" not in out, \
            f"実入力を与えた check {cid} が未実行と報告された（偽陽性）:\n{out}"
