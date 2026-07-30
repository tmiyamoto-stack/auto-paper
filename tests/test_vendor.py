# -*- coding: utf-8 -*-
"""同梱コア（vendor/core/）の完全性とドリフトの検証。

同梱は clone しただけで動くために必要だが、放置すると原本から静かに遅れる。
「古いことに誰も気づかない」壊れ方を防ぐため、毎回テストで検証する。
"""
import os

import pytest

import core
import sync_core
from conftest import core_available

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_vendored_core_exists_and_is_usable():
    """同梱コアが存在し、コアとしての要件を満たすこと（＝clone だけで動く）。"""
    assert os.path.isdir(core.VENDORED_CORE), "vendor/core/ が無い（clone しただけでは動かない）"
    assert core.is_core(core.VENDORED_CORE), \
        f"同梱コアに必須ファイルが欠けている: {core._missing(core.VENDORED_CORE)}"


def test_vendored_core_matches_provenance():
    """同梱物が PROVENANCE の sha256 と一致すること（直接編集・欠落の検出）。"""
    problems = sync_core.check()
    assert not problems, "同梱コアが記録と不一致:\n" + "\n".join(f"  - {p}" for p in problems)


def test_provenance_records_source_commit():
    import json
    with open(sync_core.PROVENANCE, encoding="utf-8") as fh:
        prov = json.load(fh)
    assert prov.get("source_commit"), "原本のコミットが記録されていない（出所不明の同梱物）"
    assert prov.get("n_files", 0) > 0
    assert set(prov.get("subtrees", [])) == {"audit", "pipeline"}


def test_vendored_core_is_importable_standalone(monkeypatch, tmp_path):
    """隣接コアが無くても同梱コアで解決できること。"""
    monkeypatch.delenv("AUTO_PAPER_CORE", raising=False)
    monkeypatch.setattr(core, "_config_core_path", lambda: None)
    monkeypatch.setattr(core, "HERE", str(tmp_path / "isolated"))   # 兄弟探索を空振りさせる
    resolved = core.resolve_core()
    assert os.path.abspath(resolved) == os.path.abspath(core.VENDORED_CORE)


def test_live_core_wins_over_vendored():
    """原本（隣接スキル）があるときは同梱物より優先されること。

    逆になると、コアを直しても古い同梱物が使われ続けて気づけない。
    """
    if not core.discover_cores():
        pytest.skip("隣接コアが無い環境（単体クローン）")
    resolved = core.resolve_core()
    assert os.path.abspath(resolved) != os.path.abspath(core.VENDORED_CORE), \
        "隣接する原本があるのに同梱物が使われている"


@pytest.mark.skipif(not core_available(), reason="コアが解決できない環境")
def test_no_drift_from_live_core():
    """原本が同梱物より先に進んでいないこと（再同期忘れの検出）。"""
    live = [p for p in core.discover_cores()
            if os.path.abspath(p) != os.path.abspath(core.VENDORED_CORE)]
    if not live:
        pytest.skip("比較対象の原本が無い（単体クローン）")
    problems = sync_core.check(source=live[0])
    assert not problems, (
        "同梱コアが原本とドリフトしている。`python3 sync_core.py --source <原本>` で再同期すること:\n"
        + "\n".join(f"  - {p}" for p in problems))
