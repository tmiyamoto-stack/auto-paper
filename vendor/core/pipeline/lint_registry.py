"""レジストリと文書・config の同期リンタ。

共同研究者レビュー指摘1（「13チェック」と書いた文書 vs 12個しか載っていない構造説明）
への構造的対処。個数を手で直しても再発するため、**文書に書かれた個数がレジストリと
一致しなければテストが落ちる**ようにする。

検査項目:

1. 文書（SKILL.md / DESIGN.md）が正準の件数行を含むこと。
2. 文書中の「N チェック」「N 個のチェック」という記述が、レジストリの規則数と一致すること
   （不一致は表記同期漏れとして FAIL）。
3. `config.yaml` の `profiles.*.checks` が、そのプロファイルで利用可能な check_id 集合と
   完全一致すること（現状は古い部分集合のまま放置されていた）。
"""
from __future__ import annotations

import json
import re

from audit.tier1 import registry

# 「…」やバッククォートで囲まれた件数記述は、過去の誤りや仮定の話を引用する
# narrative（例:「13チェック」と書いた文書）なので突合対象から外す。
_QUOTED = re.compile(r"「[^」]*」|`[^`]*`")

# 総数を主張する形（事故の元になった「13チェック」形）だけを突合対象にする。
# `(?<![.\d])` は見出し番号（"### 4.1.1 チェックレジストリ"）や "Tier1" を除外する。
# 部分集合の件数（「推論頑健性の3規則」）は正当な散文なので対象にしない——総数を
# 述べてよい場所は正準の件数行だけ、という規律で担保する。
_COUNT_PATTERNS = (
    re.compile(r"(?<![.\d])(\d+)\s*個のチェック"),
    re.compile(r"(?<![.\d])(\d+)\s*つのチェック"),
    re.compile(r"(?<![.\d])(\d+)\s*チェック(?![ァ-ヶー一-龠])"),
)


def canonical_count_line() -> str:
    """文書に必ず含めさせる正準の件数行（レジストリから生成）。"""
    j = len(registry.rules_for_profile("jastis"))
    g = len(registry.rules_for_profile("generic"))
    return (f"Tier1 規則数は jastis={j} / generic={g}"
            "（`audit/tier1/registry.py` が単一の真実）")


def lint_documents(paths: list[str]) -> list[str]:
    """文書の件数記述をレジストリと突合する。空リスト = 合格。"""
    errors: list[str] = []
    expected = {len(registry.rules_for_profile("jastis")),
                len(registry.rules_for_profile("generic"))}
    marker = canonical_count_line()

    for path in paths:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        text = raw
        # narrative の引用部は空白に潰してから件数記述を探す（位置は保つ）。
        scanned = _QUOTED.sub(lambda m: " " * len(m.group(0)), raw)
        if marker not in text:
            errors.append(f"{path}: 正準の件数行が無い（要記載: '{marker}'）")
        for pat in _COUNT_PATTERNS:
            for m in pat.finditer(scanned):
                # 正準行そのものは対象外（レジストリ生成のため常に正しい）。
                if marker[:12] in text[max(0, m.start() - 40):m.end() + 40]:
                    continue
                n = int(m.group(1))
                if n not in expected:
                    errors.append(
                        f"{path}: 件数記述 '{m.group(0)}' がレジストリ"
                        f"（{sorted(expected)}）と不一致")
    return errors


def lint_config(config_path: str) -> list[str]:
    """config の profiles.*.checks をレジストリと突合する。"""
    errors: list[str] = []
    with open(config_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    for profile, spec in (cfg.get("profiles") or {}).items():
        declared = sorted(set(spec.get("checks", [])))
        actual = sorted({r.check_id for r in registry.rules_for_profile(profile)})
        if declared != actual:
            missing = sorted(set(actual) - set(declared))
            extra = sorted(set(declared) - set(actual))
            errors.append(
                f"config profiles.{profile}.checks がレジストリと不一致 "
                f"(不足={missing}, 余剰={extra})")
    return errors
