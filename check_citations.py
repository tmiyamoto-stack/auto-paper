# -*- coding: utf-8 -*-
"""工程3b/5: 本文の引用マーカーと bibliography.json の配線を決定的に照合する。

check M（コアの引用実在確認）は「bibliography に載っている文献が実在するか」を見る。
しかし**本文と bibliography の対応**は見ていない。そのため次が素通りする:

  - 本文に [7] があるのに bibliography に7番が無い（幻覚引用の典型形）
  - bibliography に登録したのに本文で一度も引いていない（水増し）
  - 参考文献リストの番号が飛んでいる／重複している
  - 本文の最大番号がリストの件数を超えている

いずれも決定的に判定できるのでコードで潰す。

使い方:
    python3 check_citations.py --run-dir <run> \
        [--manuscript 04_manuscript/manuscript_v1_en.md] \
        [--bibliography 03_results/bibliography.json]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

CITE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")


def cited_numbers(text: str) -> set[int]:
    """本文中の [1] [2,3] [4-6] を展開して引用番号の集合を返す。"""
    body = text.split("## References")[0]        # 参考文献リスト自体は除外
    body = re.sub(r"`[^`]*`", " ", body)
    out: set[int] = set()
    for m in CITE.finditer(body):
        for part in re.split(r"\s*,\s*", m.group(1)):
            rng = re.match(r"^(\d+)\s*[–-]\s*(\d+)$", part.strip())
            if rng:
                out.update(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.strip().isdigit():
                out.add(int(part.strip()))
    return out


def bib_numbers(bib: list) -> tuple[set[int], list[str]]:
    """bibliography.json から番号集合と不備一覧を返す。"""
    nums: set[int] = set()
    problems: list[str] = []
    seen: dict[int, int] = {}
    for i, e in enumerate(bib):
        n = e.get("n") or e.get("number") or e.get("id")
        if isinstance(n, str) and n.lstrip("ref").isdigit():
            n = int(n.lstrip("ref"))
        if not isinstance(n, int):
            n = i + 1                              # 順序を番号とみなす
        seen[n] = seen.get(n, 0) + 1
        nums.add(n)
    for n, c in sorted(seen.items()):
        if c > 1:
            problems.append(f"bibliography に番号 {n} が {c} 件重複している")
    return nums, problems


def check(manuscript: str, bib: list) -> list[str]:
    problems: list[str] = []
    cited = cited_numbers(manuscript)
    listed, dup = bib_numbers(bib)
    problems += dup

    for n in sorted(cited - listed):
        problems.append(f"本文が [{n}] を引いているが bibliography に登録が無い（幻覚引用の疑い）")
    for n in sorted(listed - cited):
        problems.append(f"bibliography の {n} 番が本文で一度も引かれていない")
    if listed:
        expected = set(range(1, max(listed) + 1))
        for n in sorted(expected - listed):
            problems.append(f"参考文献の番号 {n} が欠番")
    for i, e in enumerate(bib):
        if not (e.get("doi") or e.get("pmid") or e.get("url")):
            t = str(e.get("title", ""))[:50] or f"entry[{i}]"
            problems.append(f"識別子(DOI/PMID/URL)が無い文献: {t}（実在確認できない）")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="本文の引用と bibliography の配線を照合する")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--manuscript", default=os.path.join("04_manuscript", "manuscript_v1_en.md"))
    ap.add_argument("--bibliography", default=os.path.join("03_results", "bibliography.json"))
    args = ap.parse_args(argv)

    run = os.path.abspath(os.path.expanduser(args.run_dir))
    man_p = args.manuscript if os.path.isabs(args.manuscript) else os.path.join(run, args.manuscript)
    bib_p = args.bibliography if os.path.isabs(args.bibliography) else os.path.join(run, args.bibliography)

    if not os.path.exists(man_p):
        sys.stderr.write(f"[照合できない] 原稿が無い: {man_p}\n")
        return 2
    if not os.path.exists(bib_p):
        sys.stderr.write(
            f"[照合できない] bibliography.json が無い: {bib_p}\n"
            "  引用を伴う原稿では必須。DOI/PMID 付きで作成すること（check M が実在を照会する）。\n")
        return 2

    manuscript = io.open(man_p, encoding="utf-8").read()
    try:
        bib = json.load(io.open(bib_p, encoding="utf-8"))
    except ValueError as e:
        sys.stderr.write(f"[照合できない] bibliography.json が不正: {e}\n")
        return 2
    if isinstance(bib, dict):
        bib = bib.get("references") or bib.get("bibliography") or []

    problems = check(manuscript, bib)
    cited = cited_numbers(manuscript)
    print("=" * 74)
    print(f"本文の引用番号: {len(cited)} 種 / bibliography: {len(bib)} 件")
    print("=" * 74)
    if problems:
        print("[NG] 引用の配線に不備がある:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("[OK] 本文の引用と bibliography が1対1で対応している")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
