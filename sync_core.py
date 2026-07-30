# -*- coding: utf-8 -*-
"""監査コアを vendor/core/ へ同梱（vendoring）し、原本との同一性を検証する。

## なぜ同梱するのか

本スキルは clone しただけで動く必要がある。監査コア（`audit/` の決定的チェックと
`pipeline/` のスキーマ・プロファイラ）は stdlib のみで外部依存が無いため、
同梱しても配布上の負担が無い。

## なぜ「ただのコピー」にしないのか

コピーは二重管理を生む。原本が改善されても同梱側は古いまま、しかも
**古いことに誰も気づかない**という壊れ方をする。そこで:

  - `PROVENANCE.json` に原本のコミットと全ファイルの sha256 を記録する
  - `--check` で同梱物が記録どおりか（改竄・欠落が無いか）を検証する
  - `--check --source <原本>` で原本とのドリフト（原本が先に進んでいないか）も検証する
  - テスト（tests/test_vendor.py）がこの検証を毎回走らせる

原本を編集して `python3 sync_core.py --source <原本>` を実行すれば同梱物が更新される。
**同梱物を直接編集してはならない**（次回同期で失われ、PROVENANCE と食い違う）。

使い方:
    python3 sync_core.py --source ~/.claude/skills/<コアを持つスキル>   # 同梱を更新
    python3 sync_core.py --check                                        # 同梱物の完全性を検証
    python3 sync_core.py --check --source <原本>                        # 原本とのドリフトも検証
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor")
VENDOR_CORE = os.path.join(VENDOR, "core")
PROVENANCE = os.path.join(VENDOR, "PROVENANCE.json")

# 同梱するサブツリー（監査ロジックのみ。エージェント定義や特定調査向け設定は含めない）
SUBTREES = ("audit", "pipeline")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: str):
    """同梱対象ファイルを決定的な順序で列挙する。"""
    for sub in SUBTREES:
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for fn in sorted(filenames):
                if fn.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, fn)
                yield os.path.relpath(full, root), full


def _source_commit(source: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", source, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def vendor(source: str) -> dict:
    source = os.path.abspath(os.path.expanduser(source))
    files = list(_iter_files(source))
    if not files:
        raise SystemExit(f"[error] 同梱対象が見つからない: {source} に {SUBTREES} が無い")

    if os.path.isdir(VENDOR_CORE):
        shutil.rmtree(VENDOR_CORE)
    manifest = {}
    for rel, full in files:
        dest = os.path.join(VENDOR_CORE, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(full, dest)
        manifest[rel] = _sha256(dest)

    prov = {
        "_comment": [
            "vendor/core/ は原本からの同梱物であり、直接編集してはならない。",
            "原本を編集してから sync_core.py --source <原本> を実行すること。",
            "files は同梱物の sha256。sync_core.py --check で検証される。",
        ],
        "source_commit": _source_commit(source),
        "subtrees": list(SUBTREES),
        "n_files": len(manifest),
        "files": manifest,
    }
    os.makedirs(VENDOR, exist_ok=True)
    with open(PROVENANCE, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return prov


def check(source: str | None = None) -> list[str]:
    """同梱物の完全性（と、原本があればドリフト）を検証し、問題の一覧を返す。"""
    problems: list[str] = []
    if not os.path.exists(PROVENANCE):
        return ["vendor/PROVENANCE.json が無い（同梱されていない）"]
    with open(PROVENANCE, encoding="utf-8") as fh:
        prov = json.load(fh)

    recorded = prov.get("files", {})
    present = {rel for rel, _ in _iter_files(VENDOR_CORE)}
    for rel in sorted(set(recorded) - present):
        problems.append(f"同梱物が欠落: {rel}")
    for rel in sorted(present - set(recorded)):
        problems.append(f"PROVENANCE に無いファイルが同梱されている: {rel}")
    for rel in sorted(set(recorded) & present):
        actual = _sha256(os.path.join(VENDOR_CORE, rel))
        if actual != recorded[rel]:
            problems.append(f"同梱物が記録と不一致（直接編集の疑い）: {rel}")

    if source:
        src = os.path.abspath(os.path.expanduser(source))
        src_files = {rel: _sha256(full) for rel, full in _iter_files(src)}
        for rel in sorted(set(src_files) - set(recorded)):
            problems.append(f"原本にあるが未同梱: {rel}")
        for rel in sorted(set(recorded) - set(src_files)):
            problems.append(f"同梱されているが原本に無い: {rel}")
        for rel in sorted(set(src_files) & set(recorded)):
            if src_files[rel] != recorded[rel]:
                problems.append(f"原本が先に進んでいる（要再同期）: {rel}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="監査コアの同梱と検証")
    ap.add_argument("--source", help="原本（audit/ と pipeline/ を持つディレクトリ）")
    ap.add_argument("--check", action="store_true", help="同梱物を検証する（更新しない）")
    args = ap.parse_args(argv)

    if args.check:
        problems = check(args.source)
        if problems:
            print("[NG] 同梱コアに問題がある:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("[OK] 同梱コアは PROVENANCE と一致"
              + ("（原本ともドリフト無し）" if args.source else ""))
        return 0

    if not args.source:
        ap.error("--source を指定するか --check を使うこと")
    prov = vendor(args.source)
    print(f"[OK] {prov['n_files']} ファイルを vendor/core/ へ同梱")
    print(f"     原本コミット: {prov['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
