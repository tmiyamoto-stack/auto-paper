# -*- coding: utf-8 -*-
"""工程4c: 英文校閲が「文章だけ」を直したことを決定的に検証する。

## なぜコードで検証するのか

英文校閲を LLM に任せると、文章を整える過程で**数値・引用番号・見出しが
静かに変わる**リスクがある。0.82 が 0.83 になっても英文としては自然なので、
人間の目視では捕まらない。工程4が「手書き数値ゼロ」で積み上げた保証が、
最後の校閲で壊れては意味がない。

そこで分担を固定する:

  - 文章の質（冠詞・時制・語法・流れ）は LLM が直す
  - **数値・引用番号・見出し・プレースホルダの不変性はコードが保証する**

## 検証項目（すべて決定的）

1. 数値トークンの列が完全一致すること（順序込み）
2. 引用マーカー [1] [2,3] の列が完全一致すること
3. 見出し（`#`〜`###`）の列が完全一致すること
4. 未差し込みプレースホルダ `{{...}}` が新たに出現していないこと
5. 参考文献の DOI 列が完全一致すること

いずれか1つでも違えば exit 1（校閲を差し戻す）。

使い方:
    python3 check_copyedit.py --before 04_manuscript/manuscript_v1_en.md \
                              --after  04_manuscript/manuscript_final_en.md
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

# 数値: 1.62 / 11,533 / 0.001 / -1 / 95% など。日付や版番号も含めて厳密に見る。
NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
CITE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
HEAD = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}")
DOI = re.compile(r"10\.\d{4,9}/\S+")


def numbers(text: str) -> list[str]:
    """数値トークンを出現順に返す（インラインコードは対象外）。"""
    text = re.sub(r"`[^`]*`", " ", text)
    return [m.group(0) for m in NUM.finditer(text)]


def citations(text: str) -> list[str]:
    return [re.sub(r"\s+", "", m.group(1)) for m in CITE.finditer(text)]


def headings(text: str) -> list[str]:
    return [f"{m.group(1)} {m.group(2).strip()}" for m in HEAD.finditer(text)]


def dois(text: str) -> list[str]:
    return [m.group(0).rstrip(".,;)") for m in DOI.finditer(text)]


def _first_diff(a: list, b: list) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            ctx_a = " ".join(map(str, a[max(0, i - 2):i + 3]))
            ctx_b = " ".join(map(str, b[max(0, i - 2):i + 3]))
            return f"{i+1}個目で相違: 校閲前 '{x}' → 校閲後 '{y}'\n      前後: [{ctx_a}] → [{ctx_b}]"
    if len(a) != len(b):
        longer, side = (a, "校閲前") if len(a) > len(b) else (b, "校閲後")
        return f"個数が違う（{side}に余分がある）: 余り {longer[min(len(a), len(b)):][:5]}"
    return "（差分の特定に失敗）"


def compare(before: str, after: str) -> list[str]:
    problems: list[str] = []
    for label, fn in (("数値", numbers), ("引用マーカー", citations),
                      ("見出し", headings), ("DOI", dois)):
        a, b = fn(before), fn(after)
        if a != b:
            problems.append(f"[{label}] 校閲で変化した（{len(a)}→{len(b)}件）。\n      {_first_diff(a, b)}")
    new_ph = PLACEHOLDER.findall(after)
    if new_ph:
        problems.append(f"[プレースホルダ] 校閲後に未差し込みが出現: {new_ph[:5]}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="英文校閲が文章だけを直したことを検証する")
    ap.add_argument("--before", required=True, help="校閲前（レンダ済み原稿）")
    ap.add_argument("--after", required=True, help="校閲後")
    args = ap.parse_args(argv)

    for label, p in (("校閲前", args.before), ("校閲後", args.after)):
        if not os.path.exists(p):
            sys.stderr.write(f"[検証できない] {label}のファイルが無い: {p}\n")
            return 2

    before = io.open(args.before, encoding="utf-8").read()
    after = io.open(args.after, encoding="utf-8").read()

    problems = compare(before, after)

    print("=" * 74)
    print(f"校閲前: {args.before}")
    print(f"校閲後: {args.after}")
    print("=" * 74)
    if problems:
        print("[NG] 校閲が文章以外を変更している:")
        for p in problems:
            print(f"  - {p}")
        print("\n  → 校閲を差し戻すこと。数値・引用・見出しは校閲対象外である。")
        return 1

    bw, aw = len(before.split()), len(after.split())
    print("[OK] 数値・引用マーカー・見出し・DOI はすべて不変")
    print(f"     語数: {bw} → {aw}（差 {aw - bw:+d}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
