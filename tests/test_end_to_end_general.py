# -*- coding: utf-8 -*-
"""非臨床データ（小売の売上パネル）での実走検証。

本スキルの存在意義は「臨床でない表形式データにも同じ監査が効くこと」なので、
臨床用語を一切含まないデータで、元の2大失敗クラスが実際に捕まることを固定する。

fixtures/retail.csv に仕込んだ欠陥:
  - satisfaction = 99  … 1-5 の満足度尺度における非回答コード
                          （＝旧論文の失敗①「収入19=答えたくない→2,500万円」の業務版）
  - revenue_kyen = -1  … 売上が負＝ありえない値（臨床の「年齢999」に対応）
"""
import json
import os

import pytest

import core
import domain as d
from conftest import FIXTURES

core.ensure_core_importable()

from audit.tier1.check_a_generic import check_a_generic, load_generic_codebook  # noqa: E402
from audit.tier1.check_d_outliers import check_d  # noqa: E402
from audit.tier1.findings import Status  # noqa: E402
from pipeline.profile_data import profile_csv  # noqa: E402
from pipeline.schemas import validate_generic_codebook  # noqa: E402

CSV = os.path.join(FIXTURES, "retail.csv")


@pytest.fixture(scope="module")
def profile():
    return profile_csv(CSV)


def _codebook(tmp_path, satisfaction_var):
    obj = {"variables": [
        {"name": "revenue", "source_column": "revenue_kyen"},
        {"name": "staff", "source_column": "staff_count"},
        satisfaction_var,
    ]}
    assert validate_generic_codebook(obj) == []
    p = tmp_path / "variable_codebook.json"
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)


# --- プロファイラが非臨床データでもセンチネルを見つけるか -----------------

def test_profiler_flags_99_as_sentinel_in_business_data(profile):
    sat = profile["columns"]["satisfaction"]
    cands = sat.get("sentinel_candidates") or {}
    assert 99 in set(cands.get("numeric", [])), \
        f"満足度99をセンチネル候補として検出できていない: {cands}"


# --- 失敗①の業務版: 非回答コードに実数値を割り当てる -----------------------
#
# コアの設計上、根拠の強さで重大度が分かれる（check_a_generic の Fix2）:
#   プロファイラのヒューリスティック候補のみが根拠 → INCOMPLETE（人間レビューへ）
#   ユーザー辞書が missing_codes として宣言       → 確定的 FAIL
# 「候補が実は正当な値」の誤検出でハードブロックしないための分離であり、
# どちらの場合もサイレント PASS にはならない。この2段構えを固定する。

def test_heuristic_sentinel_misuse_is_surfaced_not_passed(tmp_path, profile):
    """辞書が無い場合、99への実数値割当は INCOMPLETE として人間に surface される。"""
    bad = {
        "name": "satisfaction",
        "source_column": "satisfaction",
        "numeric_map": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "99": 99},
        "treat_as_missing": [],
    }
    findings = check_a_generic(load_generic_codebook(_codebook(tmp_path, bad)), profile, None)
    sat = [f for f in findings if f.variable == "satisfaction"]
    assert sat, "satisfaction の所見が無い"
    assert not any(f.status is Status.PASS for f in sat), \
        "非回答コード99への実数値割当がサイレント PASS になっている"
    assert any(f.status is Status.INCOMPLETE for f in sat)


def test_dictionary_declared_sentinel_misuse_is_hard_fail(tmp_path, profile):
    """辞書が 99 を missing_codes と宣言していれば、実数値割当は確定的 FAIL。"""
    bad = {
        "name": "satisfaction",
        "source_column": "satisfaction",
        "numeric_map": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "99": 99},
        "treat_as_missing": [],
    }
    user_dict = {"satisfaction": {"missing_codes": [99]}}
    findings = check_a_generic(
        load_generic_codebook(_codebook(tmp_path, bad)), profile, user_dict)
    sat = [f for f in findings if f.variable == "satisfaction"]
    assert any(f.status is Status.FAIL for f in sat), \
        f"辞書宣言済みの非回答コード誤用を FAIL にできていない: {[(f.status, f.summary) for f in sat]}"


def test_sentinel_declared_missing_passes(tmp_path, profile):
    """同じ列でも treat_as_missing に宣言すれば PASS すること（偽陽性でない）。"""
    good = {
        "name": "satisfaction",
        "source_column": "satisfaction",
        "numeric_map": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "99": None},
        "treat_as_missing": [99],
    }
    findings = check_a_generic(load_generic_codebook(_codebook(tmp_path, good)), profile, None)
    sat = [f for f in findings if f.variable == "satisfaction"]
    assert sat and not any(f.status is Status.FAIL for f in sat), \
        f"正しい宣言なのに FAIL した（偽陽性）: {[(f.status, f.summary) for f in sat]}"


# --- 「ありえない値」は臨床固有ではない ------------------------------------

def test_negative_revenue_is_critical_when_declared(profile):
    """売上が負＝ありえない値。汎用ドメインでも宣言すれば CRITICAL で捕まる。"""
    observed = {"revenue": [4820.0, 3110.0, -1.0, 6240.0]}
    k = d.build_audit_kwargs(
        "general",
        observed=observed,
        sap_plausible_ranges={"revenue": [0, 10 ** 7]},
        sap_impossible_ranges={"revenue": [0, 10 ** 9]},
    )
    findings = check_d(observed, k["outlier_ranges"], k["impossible_ranges"])
    rev = [f for f in findings if f.variable == "revenue"]
    assert any(f.status is Status.FAIL for f in rev)
    assert any(f.severity.value == "critical" for f in rev if f.status is Status.FAIL), \
        "負の売上が CRITICAL に分離されていない"


def test_unranged_column_is_surfaced_not_silently_skipped():
    """値域未宣言の列は check D が飛ばすので、その事実が警告に出ること。"""
    observed = {"revenue": [1.0], "footfall": [15300.0]}
    k = d.build_audit_kwargs("general", observed=observed,
                             sap_plausible_ranges={"revenue": [0, 10 ** 7]})
    findings = check_d(observed, k["outlier_ranges"], k["impossible_ranges"])
    assert not [f for f in findings if f.variable == "footfall"]   # コアは黙って飛ばす
    warn = d.unranged_warning(k)                                    # 本スキルが surface する
    assert warn is not None and "footfall" in warn


# --- 臨床パックが非臨床データを壊さないこと --------------------------------

def test_clinical_pack_does_not_leak_into_general_run():
    """general ドメインに臨床の既定値域が混入しない。"""
    k = d.build_audit_kwargs("general", observed={"age": [30.0]})
    assert "age" not in k["impossible_ranges"], "臨床の age 値域が general に漏れている"
    assert k["unranged_variables"] == ["age"]
