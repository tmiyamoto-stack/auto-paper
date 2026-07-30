# -*- coding: utf-8 -*-
"""工程4b: プレースホルダ原稿に results.json の値を機械的に差し込む。

## なぜこの工程が要るか

工程4は原稿に**手書き数値を一切書かない**（`{{m1.or}}` のようなプレースホルダで書く）。
これは転記エラークラスを構造的に消すための規律であり、その代償として
「差し込み工程が無いと読める原稿にならない」。従来この工程はどこにも配線されておらず、
論文ごとに自前のレンダスクリプトを書いていた。本ファイルがその汎用版である。

## 差し込みの規則

  {{path.to.value}}        そのまま文字列化
  {{path.to.value:.2f}}    Python の書式指定（小数2桁）
  {{path.to.value:,}}      3桁カンマ区切り
  {{rows.0.or:.2f}}        リストは添字で辿る

## fail-closed

- 解決できないプレースホルダが1つでもあれば**書き出さずに exit 2**（全件を列挙する）。
  部分的に埋まった原稿を出すと、埋まらなかった箇所が本文に紛れて投稿される。
- 差し込み後に `{{` が残っていれば exit 2（書式ミスの取りこぼし防止）。
- 語数上限を指定した場合、超過は exit 1（原稿は書き出す。推敲対象として提示する）。

使い方:
    python3 render_manuscript.py --run-dir <run> \
        [--template 04_manuscript/manuscript_en.md] \
        [--out 04_manuscript/manuscript_v1_en.md] \
        [--limits '{"body":4000,"abstract":250}']
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")


class Unresolved(Exception):
    pass


def resolve(path: str, data):
    """ドットパスで results.json を辿る。リストは添字で辿れる。"""
    node = data
    for part in path.split("."):
        if isinstance(node, dict):
            if part not in node:
                raise Unresolved(path)
            node = node[part]
        elif isinstance(node, (list, tuple)):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                raise Unresolved(path)
        else:
            raise Unresolved(path)
    return node


def render(template: str, data: dict) -> tuple[str, list[str]]:
    """差し込み結果と、解決できなかったキー一覧を返す。"""
    missing: list[str] = []

    def sub(m):
        raw = m.group(1).strip()
        key, _, spec = raw.partition(":")
        try:
            val = resolve(key.strip(), data)
        except Unresolved:
            if key.strip() not in missing:
                missing.append(key.strip())
            return m.group(0)
        if spec:
            try:
                return format(val, spec.strip())
            except (ValueError, TypeError):
                if raw not in missing:
                    missing.append(f"{key.strip()}（書式 '{spec.strip()}' を適用できない値: {val!r}）")
                return m.group(0)
        return str(val)

    return PLACEHOLDER.sub(sub, template), missing


# --- 語数（投稿規定の実測） ---------------------------------------------------

def _words(text: str) -> list[str]:
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[*_#\[\]]", " ", text)
    return [w for w in text.split() if re.search(r"[A-Za-z0-9]", w)]


def count_sections(rendered: str) -> dict:
    """本文・抄録の語数を実測する（表行・見出し・図表キャプションを除外）。"""
    lines = rendered.split("\n")

    def span(start_pat, end_pat):
        s = e = None
        for i, l in enumerate(lines):
            if s is None and re.match(start_pat, l):
                s = i
            elif s is not None and re.match(end_pat, l):
                e = i
                break
        return s, e

    def count(seq):
        n = 0
        for l in seq:
            st = l.strip()
            if not st or st.startswith("|") or st.startswith("#"):
                continue
            if re.match(r"^\*\*(Table|Figure)\b", st):
                continue
            n += len(_words(l))
        return n

    out = {}
    a_s, a_e = span(r"^##\s+Abstract", r"^##\s+Introduction")
    if a_s is not None and a_e is not None:
        out["abstract"] = count(lines[a_s + 1:a_e])
    b_s, b_e = span(r"^##\s+Introduction", r"^##\s+References")
    if b_s is not None:
        out["body"] = count(lines[b_s:b_e if b_e else len(lines)])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="プレースホルダ原稿に results.json を差し込む")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--template", default=os.path.join("04_manuscript", "manuscript_en.md"))
    ap.add_argument("--out", default=os.path.join("04_manuscript", "manuscript_v1_en.md"))
    ap.add_argument("--results", default=os.path.join("03_results", "results.json"))
    ap.add_argument("--limits", help='語数上限の JSON 例: {"body":4000,"abstract":250}')
    args = ap.parse_args(argv)

    run = os.path.abspath(os.path.expanduser(args.run_dir))
    tpl_p = args.template if os.path.isabs(args.template) else os.path.join(run, args.template)
    res_p = args.results if os.path.isabs(args.results) else os.path.join(run, args.results)
    out_p = args.out if os.path.isabs(args.out) else os.path.join(run, args.out)

    for label, p in (("テンプレート原稿", tpl_p), ("results.json", res_p)):
        if not os.path.exists(p):
            sys.stderr.write(f"[レンダできない] {label} が無い: {p}\n")
            return 2

    template = io.open(tpl_p, encoding="utf-8").read()
    try:
        data = json.load(io.open(res_p, encoding="utf-8"))
    except ValueError as e:
        sys.stderr.write(f"[レンダできない] results.json が不正: {e}\n")
        return 2

    rendered, missing = render(template, data)

    if missing:
        sys.stderr.write(
            f"[レンダできない] 解決できないプレースホルダ {len(missing)} 件。"
            "部分的に埋まった原稿は書き出さない:\n")
        for k in missing:
            sys.stderr.write(f"  - {{{{{k}}}}}\n")
        sys.stderr.write("  → 工程3で results.json に該当キーを出力するか、原稿側のキー名を直すこと。\n")
        return 2

    if "{{" in rendered:
        i = rendered.find("{{")
        sys.stderr.write(f"[レンダできない] 差し込み後に未処理の '{{{{' が残っている: "
                         f"{rendered[i:i+60]!r}\n")
        return 2

    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    io.open(out_p, "w", encoding="utf-8").write(rendered)
    n_ph = len({m.group(1).split(":")[0].strip() for m in PLACEHOLDER.finditer(template)})
    print(f"rendered: {n_ph} 個のプレースホルダを差し込み -> {out_p}")

    counts = count_sections(rendered)
    if counts:
        print("語数（実測。表行・見出し・図表キャプション・インラインコードを除外）:")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")

    over = []
    if args.limits:
        try:
            limits = json.loads(args.limits)
        except ValueError:
            sys.stderr.write("[警告] --limits が JSON として読めない。語数判定を行わない\n")
            limits = {}
        for k, lim in limits.items():
            if k in counts and counts[k] > lim:
                over.append(f"{k}: {counts[k]} > {lim}")
    if over:
        print("[語数超過] 投稿規定を超えている:")
        for o in over:
            print(f"  - {o}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
