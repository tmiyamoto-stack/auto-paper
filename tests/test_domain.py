# -*- coding: utf-8 -*-
"""ドメイン参照パックの検証。

固定したい性質:
  - ドメイン未宣言は例外（暗黙に general へ倒さない）
  - SAP 宣言がパック既定値に勝つ
  - 値域未宣言の観測変数は警告として surface される（黙って飛ばさない）
  - general パックが空でも「チェックしない」意味にならない
"""
import pytest

import domain as d


def test_known_domains_present():
    avail = d.available_domains()
    for name in ("clinical", "survey", "general"):
        assert name in avail


def test_domain_required_no_implicit_default():
    with pytest.raises(d.DomainError):
        d.load_pack(None)
    with pytest.raises(d.DomainError):
        d.load_pack("")


def test_unknown_domain_rejected():
    with pytest.raises(d.DomainError) as e:
        d.load_pack("astrology")
    assert "astrology" in str(e.value)


def test_clinical_pack_has_reference_data():
    k = d.build_audit_kwargs("clinical")
    assert k["impossible_ranges"]["age"] == (0, 120)
    assert k["unit_plausible"]["mg/dL"] == (70.0, 200.0)


def test_general_pack_is_empty_but_valid():
    k = d.build_audit_kwargs("general")
    assert k["impossible_ranges"] == {}
    assert k["unit_plausible"] == {}
    assert k["domain"] == "general"


def test_sap_declaration_overrides_pack():
    """研究ごとの SAP 宣言がパック既定値に勝つ。"""
    k = d.build_audit_kwargs(
        "clinical",
        sap_impossible_ranges={"age": [18, 65]},
    )
    assert k["impossible_ranges"]["age"] == (18, 65)


def test_sap_can_add_ranges_to_general_domain():
    """汎用ドメインでも宣言すれば臨床と同じ強度で値域照合される。"""
    k = d.build_audit_kwargs(
        "general",
        sap_impossible_ranges={"revenue_kyen": [0, 1000000]},
        sap_plausible_ranges={"staff_count": [1, 200]},
    )
    assert k["impossible_ranges"]["revenue_kyen"] == (0, 1000000)
    assert k["outlier_ranges"]["staff_count"] == (1, 200)


def test_unranged_variables_are_surfaced():
    """値域を宣言していない観測変数は警告に出る（サイレントに飛ばさない）。"""
    k = d.build_audit_kwargs(
        "general",
        observed={"revenue_kyen": [100.0], "footfall": [3.0]},
        sap_plausible_ranges={"revenue_kyen": [0, 10 ** 9]},
    )
    assert k["unranged_variables"] == ["footfall"]
    warn = d.unranged_warning(k)
    assert warn is not None and "footfall" in warn


def test_no_warning_when_all_ranged():
    k = d.build_audit_kwargs(
        "general",
        observed={"revenue_kyen": [100.0]},
        sap_plausible_ranges={"revenue_kyen": [0, 10 ** 9]},
    )
    assert k["unranged_variables"] == []
    assert d.unranged_warning(k) is None


def test_malformed_range_rejected():
    with pytest.raises(d.DomainError):
        d.build_audit_kwargs("general", sap_plausible_ranges={"x": [1, 2, 3]})
