import os
import sys

# スキルルート（core.py / domain.py の所在）を import path に入れる
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def core_available() -> bool:
    """共有監査コアを解決できるか。

    本スキルを単体でクローンした場合（skills 配下にコアが無い）はコアに依存する
    テストを実行できない。README のとおりコアを持つスキルと同じディレクトリに
    置けば実行される。欠陥ではないので fail ではなく skip にする。
    """
    import core
    try:
        core.resolve_core()
        return True
    except Exception:
        return False


def _requires_core_marker():
    import pytest
    return pytest.mark.skipif(
        not core_available(),
        reason="隣接する監査コアが無い（単体クローン）。skills 配下にコアを置くと実行される")


requires_core = _requires_core_marker()
