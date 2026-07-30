# -*- coding: utf-8 -*-
"""共有監査コアの解決。

本スキルは監査コア（`audit/`・`pipeline/`）を**複製しない**。コアは別スキルが
保持する単一の実装を唯一の真実として参照する。したがってコアの検査が改善されれば
本スキルにも同時に効き、二重管理が発生しない。

本スキルが自前で持つのは次の4つだけである:
  - SKILL.md（説明・トリガ）
  - config.yaml（配線）
  - agents/（ドメイン非依存の工程1〜4プロンプト）
  - references/domains/*.json（ドメイン別の参照データ＝値域・単位の基準）

## コアの特定は「名前」ではなく「構造」で行う

コアのディレクトリ名をハードコードすると、コア側がリネーム/移動しただけで壊れ、
しかも壊れ方が「別のものを掴む」形になりうる。そこで既定の解決は、
skills ディレクトリを走査して**コアの必須ファイル一式を備えたディレクトリ**を
探す方式にしてある（`_REQUIRED`）。候補が複数見つかった場合は曖昧なので
自動選択せず、明示指定を要求して失敗する（fail-closed）。

解決順序（先に見つかったものを採用）:
  1. 明示指定（`resolve_core(explicit=...)`／`--core`）
  2. 環境変数 `AUTO_PAPER_CORE`
  3. config.yaml の `core_skill_path`（`~` と相対パスを解決）
  4. 兄弟ディレクトリの構造探索（名前非依存）

1 と 2 は利用者の明示指定なので、不正なら**フォールバックせず即座に失敗**する。
指定を無視して別のコアで監査すると、取り違えに気づけないまま「成功」して見える。

コアが見つからない場合も明示的に失敗する。監査を実行しないまま正常終了する経路は
作らない。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.yaml")

# コアと認めるために存在を要求するファイル（誤ったディレクトリを掴まないため）
_REQUIRED = (
    os.path.join("audit", "tier1", "runner.py"),
    os.path.join("audit", "tier1", "findings.py"),
    os.path.join("pipeline", "profile_data.py"),
    os.path.join("pipeline", "schemas.py"),
)

# 利用者が明示的に指定した経路。不正なとき黙って別のコアへ倒れてはならない。
_HARD_ORIGINS = ("explicit", "env:AUTO_PAPER_CORE")


class CoreNotFound(RuntimeError):
    """共有監査コアを解決できなかった。"""


class CoreAmbiguous(RuntimeError):
    """コア候補が複数あり、自動では選べない。"""


def _missing(path: str) -> list[str]:
    return [r for r in _REQUIRED if not os.path.exists(os.path.join(path, r))]


def is_core(path: str) -> bool:
    return os.path.isdir(path) and not _missing(path)


def _config_core_path() -> str | None:
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return None
    raw = data.get("core_skill_path")
    if not raw:
        return None
    raw = os.path.expanduser(raw)
    return raw if os.path.isabs(raw) else os.path.normpath(os.path.join(HERE, raw))


def discover_cores(skills_dir: str | None = None) -> list[str]:
    """兄弟ディレクトリを走査してコアの要件を満たすものを返す（名前非依存・決定的）。"""
    root = skills_dir or os.path.dirname(HERE)
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        cand = os.path.join(root, name)
        if os.path.abspath(cand) == os.path.abspath(HERE):
            continue          # 自分自身は対象外
        if is_core(cand):
            out.append(os.path.abspath(cand))
    return out


def resolve_core(explicit: str | None = None) -> str:
    """共有コアの絶対パスを返す。見つからなければ CoreNotFound を送出する。"""
    tried: list[str] = []

    for origin, raw in (("explicit", explicit),
                        ("env:AUTO_PAPER_CORE", os.environ.get("AUTO_PAPER_CORE")),
                        ("config.yaml:core_skill_path", _config_core_path())):
        if not raw:
            continue
        path = os.path.abspath(os.path.expanduser(raw))
        if is_core(path):
            return path
        reason = ("ディレクトリが存在しない" if not os.path.isdir(path)
                  else f"コアの必須ファイル欠落: {', '.join(_missing(path))}")
        tried.append(f"  [{origin}] {path} — {reason}")
        if origin in _HARD_ORIGINS:
            raise CoreNotFound(
                f"明示指定された共有コアが不正である（{origin}）。\n"
                f"  {path} — {reason}\n"
                "指定を無視して別のコアで監査すると取り違えに気づけないため、"
                "フォールバックせずに中止する。"
            )

    found = discover_cores()
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise CoreAmbiguous(
            "共有監査コアの候補が複数見つかり、自動では選べない:\n"
            + "\n".join(f"  - {p}" for p in found)
            + "\nどれで監査したかが曖昧なまま進めないため中止する。"
            "\n対処: config.yaml の core_skill_path か環境変数 AUTO_PAPER_CORE で1つに定めること。"
        )

    raise CoreNotFound(
        "共有監査コア（audit/ と pipeline/ を備えたスキル）を解決できなかった。\n"
        "本スキルはコアを複製せず参照する設計のため、コアが無いと監査を実行できない。\n"
        + ("試した候補:\n" + "\n".join(tried) + "\n" if tried else "")
        + f"兄弟ディレクトリ（{os.path.dirname(HERE)}）にも該当が無い。\n"
        "対処: config.yaml の core_skill_path を実在するコアへ向けるか、"
        "環境変数 AUTO_PAPER_CORE を設定すること。"
    )


def ensure_core_importable(explicit: str | None = None) -> str:
    """コアを sys.path に載せ、そのパスを返す（冪等）。"""
    core = resolve_core(explicit)
    if core not in sys.path:
        sys.path.insert(0, core)
    return core


def load_config(path: str | None = None) -> dict:
    """本スキルの config.yaml（中身は JSON）を読む。"""
    with open(path or CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)
