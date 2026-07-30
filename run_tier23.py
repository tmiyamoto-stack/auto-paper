# -*- coding: utf-8 -*-
"""工程5b: Tier2/3（外部モデルによる独立監査と裁定）を実走する。

## この工程が何をするか

`run_audit.py`（Tier1・決定的チェック）が出した findings のうち、**機械では
閉じられないもの**（FAIL / INCOMPLETE、および定性判断を要する項目）を、
生成に使ったモデル系列を除外した外部監査者へ回し、verdict を集約する。

従来この工程は `agents/05_audit.md` というプロンプトだけがあり、モデルを
起動する経路はコードに無かった（`audit/external/` は runner を注入で受け取る
判定ロジック層）。本ファイルがその runner を与える。

## 利益相反（COI）の扱い

監査者の選定は `audit.external.matrix.select_auditors(generator_model, models_cfg)`
に委ねる。**本ファイルは選定ロジックを持たない**（持つと二重実装になり、
COI 規則が静かにずれる）。既定配置では:

  - Sol（codex）      = クリティカル一次監査
  - Gemini            = 独立第二票
  - Fable             = Claude 系列のため、生成物が Claude 製ならクリティカル
                        一次監査から除外され、不一致時の第三票としてのみ働く

## fail-closed

- 監査者が1人も使えない → exit 2（監査を実行できなかった）
- あるモデルが利用不可・応答不正 → そのモデルの verdict は INCOMPLETE。
  **黙って人数を減らして「合意」にしない。**
- クリティカルに FAIL/INCOMPLETE が一票でもあれば ESCALATE_HUMAN。

## 盲検

監査者には findings と一次証拠のみを渡し、生成経緯（プロンプト履歴・
中間検討）を渡さない。verdict の `model` / `finding_id` / `blinded` は
ハーネスが権威として上書きする（モデルの自己申告を信用しない）。

## CLI から起動できないモデル（Fable 等）の扱い

codex と gemini は CLI があるので本ファイルが直接起動する。一方 **Fable は CLI を
持たず、統括（Claude）が Agent 経由でしか起動できない**。そのモデルが監査者に
選ばれた場合、本ファイルは起動できないので既定では INCOMPLETE を計上する
（＝黙って人数を減らして「合意」にしない）。

統括が Agent で verdict を取得したら、`--inject` で渡すことで正規の一票として
集約に参加させられる:

    python3 run_tier23.py ... --inject fable=/path/to/fable_verdicts.json

注入ファイルの形式（finding_id -> verdict）:

    {"X::summary...": {"status": "fail", "severity": "critical", "evidence": "..."}}

注入された verdict も `model` / `finding_id` / `blinded` はハーネスが上書きする
（モデルの自己申告を信用しない規律は注入経路でも同じ）。

使い方:
    python3 run_tier23.py --run-dir <run> --findings findings.json \
        [--generator-model claude] [--dry-run] [--timeout 300] \
        [--inject fable=verdicts.json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

import core

PROMPT_TEMPLATE = """You are an independent auditor of a research manuscript.
You have NOT seen how this manuscript was produced. Judge only what is shown.

FINDING UNDER REVIEW
  id:       {fid}
  check:    {check}
  status:   {status} (severity: {severity})
  summary:  {summary}
  evidence: {evidence}

RUBRIC
{rubric}

TASK
Decide whether this finding represents a real defect that must block submission.
Base your judgement ONLY on the evidence shown. If you cannot judge because the
evidence is insufficient, return INCOMPLETE — do NOT guess and do NOT return PASS
to be agreeable.

Return EXACTLY ONE JSON object and nothing else:
{{"status": "pass" | "fail" | "incomplete",
  "severity": "critical" | "major" | "minor",
  "evidence": "<your concrete reasoning, citing the specific numbers or text above>"}}
"""

RUBRIC_HINT = """Judge on: (1) is the stated defect factually present in the evidence?
(2) would it change a reader's interpretation of the results?
(3) is the claim in the manuscript stronger than the evidence supports?
A finding that is real but cosmetic is 'minor'. A finding that changes conclusions
is 'critical'. If evidence is insufficient to tell, that is 'incomplete'."""


# --- モデル起動 runner（本ファイルの本体的責務） ---------------------------

def build_command(model: str, prompt_path: str) -> list[str] | None:
    """モデル名 -> 実際に叩くコマンド。未知モデルは None（＝INCOMPLETE 扱い）。"""
    if model == "codex":
        return ["codex", "exec", "--", f"@{prompt_path}"]
    if model == "gemini":
        return ["gemini", "-p", f"@{prompt_path}"]
    return None


def probe(model: str) -> bool:
    """モデルが実際に起動可能か（CLI が PATH にあるか）。"""
    cmd = build_command(model, "/dev/null")
    return bool(cmd) and shutil.which(cmd[0]) is not None


def run_model(model: str, prompt_path: str, timeout: int) -> str:
    cmd = build_command(model, prompt_path)
    if cmd is None:
        raise RuntimeError(f"モデル {model} の起動方法が未定義")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{model} exit {p.returncode}: {(p.stderr or '')[:200]}")
    return p.stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tier2/3 外部監査を実走する")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--findings", required=True, help="run_audit.py --json の出力")
    ap.add_argument("--generator-model", default="claude", help="生成に使ったモデル系列（COI 除外の基準）")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="監査者の選定と対象件数だけ表示して終了")
    ap.add_argument("--out", help="Tier2/3 結果の JSON 出力先")
    ap.add_argument("--inject", action="append", default=[],
                    help="CLI 起動できないモデルの verdict を注入 (例: fable=verdicts.json)。複数可")
    args = ap.parse_args(argv)

    run = os.path.abspath(os.path.expanduser(args.run_dir))
    if not os.path.isdir(run):
        sys.stderr.write(f"[Tier2/3 を実行できない] --run-dir が無い: {run}\n")
        return 2
    if not os.path.exists(args.findings):
        sys.stderr.write(
            f"[Tier2/3 を実行できない] findings が無い: {args.findings}\n"
            "  先に `run_audit.py --json findings.json` を実行すること。\n")
        return 2

    try:
        core.ensure_core_importable()
    except (core.CoreNotFound, core.CoreAmbiguous) as e:
        sys.stderr.write(f"[Tier2/3 を実行できない] {e}\n")
        return 2

    from audit.external.matrix import select_auditors
    from audit.external.aggregate import aggregate_finding
    from audit.external.debate import adjudicate
    from audit.external.verdict import Verdict, validate_verdict, parse_verdict
    from audit.tier1.findings import Status, Severity

    cfg = core.load_config()
    try:
        data = json.load(open(args.findings, encoding="utf-8"))
    except ValueError as e:
        sys.stderr.write(f"[Tier2/3 を実行できない] findings が不正: {e}\n")
        return 2

    # Tier2 へ回すのは「機械で閉じられなかったもの」だけ（PASS は回さない）
    targets = [f for f in data.get("findings", [])
               if f.get("status") in ("fail", "incomplete")]

    auditors = select_auditors(args.generator_model, cfg.get("models", {}))
    if not auditors:
        sys.stderr.write(
            "[Tier2/3 を実行できない] COI 除外の結果、監査者が0人になった。\n"
            f"  生成モデル系列={args.generator_model} / models={cfg.get('models')}\n")
        return 2

    injected: dict[str, dict] = {}
    for spec in args.inject:
        model, _, path = spec.partition("=")
        if not path or not os.path.exists(path):
            sys.stderr.write(f"[Tier2/3 を実行できない] --inject の指定が不正: {spec}\n")
            return 2
        try:
            injected[model.strip()] = json.load(open(path, encoding="utf-8"))
        except ValueError as e:
            sys.stderr.write(f"[Tier2/3 を実行できない] 注入ファイルが不正: {path} — {e}\n")
            return 2

    available = [m for m in auditors if probe(m) or m in injected]
    unavailable = [m for m in auditors if m not in available]

    print("=" * 74)
    print(f"生成モデル系列 : {args.generator_model}（この系列はクリティカル監査から除外される）")
    print(f"選定された監査者: {', '.join(auditors)}")
    if injected:
        print(f"verdict 注入    : {', '.join(sorted(injected))}（統括が Agent 経由で取得したもの）")
    if unavailable:
        print(f"起動不可        : {', '.join(unavailable)} → その票は INCOMPLETE として計上する")
    print(f"Tier2 対象      : {len(targets)} 件（Tier1 の FAIL / INCOMPLETE）")
    print("=" * 74)

    if args.dry_run:
        return 0
    if not available:
        sys.stderr.write("[Tier2/3 を実行できない] 選定された監査者を1人も起動できない\n")
        return 2

    tmpdir = os.path.join(run, "05_audit", "_tier23_prompts")
    os.makedirs(tmpdir, exist_ok=True)

    results = []
    escalate = 0
    for f in targets:
        fid = f"{f.get('check_id','?')}::{(f.get('variable') or f.get('summary',''))[:40]}"
        critical = (f.get("severity") == "critical")
        prompt = PROMPT_TEMPLATE.format(
            fid=fid, check=f.get("check_id", "?"), status=f.get("status", "?"),
            severity=f.get("severity", "?"), summary=f.get("summary", ""),
            evidence=(f.get("evidence") or "")[:1500], rubric=RUBRIC_HINT)
        ppath = os.path.join(tmpdir, f"{abs(hash(fid)) % 10**8}.txt")
        with open(ppath, "w", encoding="utf-8") as fh:
            fh.write(prompt)

        verdicts = []
        for m in auditors:
            if m in injected:
                obj = injected[m].get(fid)
                if obj is None or validate_verdict(obj):
                    verdicts.append(Verdict(m, fid, Status.INCOMPLETE, Severity.CRITICAL,
                                            f"{m} の注入 verdict が無い/不正"))
                else:
                    v = parse_verdict(obj)
                    v.model, v.finding_id, v.blinded = m, fid, True
                    verdicts.append(v)
                continue
            if m not in available:
                verdicts.append(Verdict(m, fid, Status.INCOMPLETE, Severity.CRITICAL,
                                        f"{m} は起動できず判定不能（CLI 非対応。--inject で渡せる）"))
                continue
            try:
                out = run_model(m, ppath, args.timeout)
                objs = []
                dec = json.JSONDecoder()
                i = 0
                while i < len(out):
                    if out[i] == "{":
                        try:
                            o, end = dec.raw_decode(out[i:])
                            if isinstance(o, dict):
                                objs.append(o)
                            i += end
                            continue
                        except ValueError:
                            pass
                    i += 1
                valid = [o for o in objs if not validate_verdict(o)]
                if not valid:
                    verdicts.append(Verdict(m, fid, Status.INCOMPLETE, Severity.CRITICAL,
                                            f"{m} の出力から有効な verdict を抽出できない"))
                    continue
                v = parse_verdict(valid[-1])
                v.model, v.finding_id, v.blinded = m, fid, True   # 自己申告を信用しない
                verdicts.append(v)
            except Exception as e:
                verdicts.append(Verdict(m, fid, Status.INCOMPLETE, Severity.CRITICAL,
                                        f"{m} 起動失敗: {str(e)[:150]}"))

        outcome = aggregate_finding(verdicts, critical)
        adj_reason = ""
        if str(getattr(outcome, "value", outcome)).upper().find("UNRESOLVED") >= 0:
            outcome, adj_reason = adjudicate(verdicts, critical)

        oname = str(getattr(outcome, "value", outcome))
        if "ESCALATE" in oname.upper():
            escalate += 1
        results.append({
            "finding_id": fid, "critical": critical, "outcome": oname,
            "adjudication": adj_reason,
            "verdicts": [{"model": v.model, "status": v.status.value,
                          "severity": v.severity.value, "evidence": v.evidence[:300]}
                         for v in verdicts],
        })
        print(f"[{oname}] {fid}")
        for v in verdicts:
            print(f"    {v.model:8s} {v.status.value:10s} {v.evidence[:80]}")

    print("=" * 74)
    print(f"Tier2/3 完了: {len(results)} 件 / ESCALATE_HUMAN {escalate} 件")

    out_p = args.out or os.path.join(run, "05_audit", "tier23_report.json")
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as fh:
        json.dump({"generator_model": args.generator_model, "auditors": auditors,
                   "unavailable": unavailable, "results": results},
                  fh, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"書き出し: {out_p}")

    return 1 if escalate else 0


if __name__ == "__main__":
    raise SystemExit(main())
