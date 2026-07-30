# -*- coding: utf-8 -*-
"""共有コア解決の検証。

本スキルの設計上の生命線は「コアを複製せず参照する」ことなので、
参照が壊れたときに**黙って動かない**のではなく**明示的に失敗する**ことを固定する。
"""
import os

import pytest

import core


def test_resolves_real_core():
    path = core.resolve_core()
    assert os.path.isdir(path)
    assert os.path.exists(os.path.join(path, "audit", "tier1", "runner.py"))


def test_core_is_importable_after_ensure():
    core.ensure_core_importable()
    from audit.tier1.runner import run_tier1_generic  # noqa: F401
    from pipeline.profile_data import profile_csv  # noqa: F401


def test_ensure_is_idempotent():
    import sys
    p1 = core.ensure_core_importable()
    n1 = sys.path.count(p1)
    p2 = core.ensure_core_importable()
    assert p1 == p2
    assert sys.path.count(p1) == n1


def test_explicit_path_wins(tmp_path):
    """明示指定が最優先されること。"""
    real = core.resolve_core()
    assert core.resolve_core(explicit=real) == os.path.abspath(real)


def test_missing_core_raises_not_silently_passes(tmp_path, monkeypatch):
    """コアが無いとき例外になる（＝監査を素通りさせない）。"""
    empty = tmp_path / "not-a-core"
    empty.mkdir()
    monkeypatch.setenv("AUTO_PAPER_CORE", str(empty))
    monkeypatch.setattr(core, "_config_core_path", lambda: str(empty))
    monkeypatch.setattr(core, "HERE", str(tmp_path / "skill"))
    with pytest.raises(core.CoreNotFound) as e:
        core.resolve_core()
    # どこを試して何が欠けていたかが読めること
    assert "必須ファイル欠落" in str(e.value) or "存在しない" in str(e.value)


def test_partial_core_is_rejected(tmp_path, monkeypatch):
    """audit/ だけあって pipeline/ が無い等の中途半端なディレクトリを掴まない。"""
    fake = tmp_path / "half-core"
    (fake / "audit" / "tier1").mkdir(parents=True)
    (fake / "audit" / "tier1" / "runner.py").write_text("")
    (fake / "audit" / "tier1" / "findings.py").write_text("")
    monkeypatch.setenv("AUTO_PAPER_CORE", str(fake))
    monkeypatch.setattr(core, "_config_core_path", lambda: None)
    monkeypatch.setattr(core, "HERE", str(tmp_path / "skill"))
    with pytest.raises(core.CoreNotFound):
        core.resolve_core()


def test_config_is_readable_json():
    cfg = core.load_config()
    assert "core_skill_path" in cfg
    assert cfg["profiles"]["default"]["primary_source"] == "data_profile"


# --- 明示指定が不正なら黙って別コアへ倒れないこと ---------------------------

def test_invalid_env_core_does_not_fall_back(monkeypatch, tmp_path):
    """AUTO_PAPER_CORE が不正なとき、config の既定値へ黙って倒れない。

    倒れてしまうと「指定したのとは別のコアで監査され、しかも成功して見える」ため、
    本スキルが防ごうとしている取り違えそのものになる。
    """
    monkeypatch.setenv("AUTO_PAPER_CORE", str(tmp_path / "nope"))
    with pytest.raises(core.CoreNotFound) as e:
        core.resolve_core()
    assert "明示指定" in str(e.value)


def test_invalid_explicit_arg_does_not_fall_back(tmp_path):
    with pytest.raises(core.CoreNotFound) as e:
        core.resolve_core(explicit=str(tmp_path / "nope"))
    assert "明示指定" in str(e.value)


def test_valid_env_core_is_used(monkeypatch):
    real = core.resolve_core()
    monkeypatch.setenv("AUTO_PAPER_CORE", real)
    assert core.resolve_core() == os.path.abspath(real)


# --- コアの特定は名前ではなく構造で行う -------------------------------------

def test_discovery_finds_core_by_structure():
    """ディレクトリ名に依存せず、必須ファイル一式の有無でコアを見つける。

    本スキルを単体でクローンした場合（隣にコアが無い）は検証不能なのでスキップする。
    README のとおり、コアを持つスキルと同じ skills ディレクトリに置く必要がある。
    """
    found = core.discover_cores()
    if not found:
        pytest.skip("隣接するコアが無い（単体クローン）。skills 配下にコアを置くと実行される")
    for p in found:
        assert core.is_core(p)


def test_discovery_excludes_self():
    assert os.path.abspath(core.HERE) not in core.discover_cores()


def test_resolution_works_without_configured_name(monkeypatch):
    """config が名前を持たなくても（core_skill_path=null）解決できる。"""
    monkeypatch.delenv("AUTO_PAPER_CORE", raising=False)
    monkeypatch.setattr(core, "_config_core_path", lambda: None)
    if not core.discover_cores():
        pytest.skip("隣接するコアが無い（単体クローン）")
    assert core.is_core(core.resolve_core())


def test_ambiguous_cores_fail_closed(tmp_path, monkeypatch):
    """コア候補が複数あるとき、どれかを勝手に選ばず失敗する。"""
    skills = tmp_path / "skills"
    for name in ("core-a", "core-b"):
        d = skills / name
        (d / "audit" / "tier1").mkdir(parents=True)
        (d / "pipeline").mkdir(parents=True)
        for rel in ("audit/tier1/runner.py", "audit/tier1/findings.py",
                    "pipeline/profile_data.py", "pipeline/schemas.py"):
            (d / rel).write_text("")
    monkeypatch.delenv("AUTO_PAPER_CORE", raising=False)
    monkeypatch.setattr(core, "_config_core_path", lambda: None)
    monkeypatch.setattr(core, "HERE", str(skills / "auto-paper"))
    with pytest.raises(core.CoreAmbiguous) as e:
        core.resolve_core()
    assert "複数" in str(e.value)


# --- コアとの契約（M4: コア変更の検知） --------------------------------------

def test_core_accepts_every_kwarg_the_driver_passes():
    """ドライバが渡す kwargs をコアの run_tier1_generic が全て受理すること。

    コアは別スキルが保持しており、こちらの知らないうちに改名・削除されうる。
    シグネチャ契約をテストで固定しておかないと、変更が TypeError（exit 2）か、
    最悪は無音の意味変化として現れる。
    """
    import inspect
    core.ensure_core_importable()
    from audit.tier1.runner import run_tier1_generic
    accepted = set(inspect.signature(run_tier1_generic).parameters)
    import run_audit  # noqa: F401  — CHECK_REQUIREMENTS の整合も併せて見る
    driver_passes = {
        "codebook_path", "data_csv_path", "methods_claims_path", "code_filters_path",
        "user_dictionary_path", "data_profile", "outlier_observed", "outlier_ranges",
        "impossible_ranges", "declared_units", "observed_unit_center", "unit_plausible",
        "flow", "claimed_ns", "bibliography", "censored_by_column",
        "censored_declared_handled", "immortal_subjects", "immortal_exposure_type",
        "missing_rates", "missingness_reported", "labels_by_source", "section_texts",
        "study_design", "sample_type", "limitations_text", "inference", "style_sections",
    }
    missing = sorted(driver_passes - accepted)
    assert not missing, f"コアが受理しない kwargs をドライバが渡している: {missing}"


def test_declared_checks_all_have_documented_requirements():
    """config の checks 全てに『何を供給すれば走るか』の説明があること。"""
    import run_audit
    cfg = core.load_config()
    declared = cfg["profiles"]["default"]["checks"]
    missing = [c for c in declared if c not in run_audit.CHECK_REQUIREMENTS]
    assert not missing, f"必要入力が未文書のチェック: {missing}"
