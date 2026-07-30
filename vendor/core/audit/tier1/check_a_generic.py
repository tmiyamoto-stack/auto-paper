"""Check A（generic プロファイル版）: 汎用コーディング照合。

一次ソース = 自動データプロファイル（`pipeline.profile_data`）＋任意ユーザー辞書。
既存 `check_a_coding`（JASTIS 設問票照合）と同じ Finding 契約（check_id="A",
Severity.CRITICAL）で並置し、既存の挙動には一切触れない。

検出クラス（DESIGN_generic_clinical.md §4.3）:
- (i) センチネル/欠損コードへの実数値割当（treat_as_missing 未宣言）
      ＝旧論文の失敗①（収入変数の非回答コード混入）の臨床一般化。
- (ii) 列ドメイン外の recode（存在しない生値への割当＝転記/取り違え）。
- 辞書・プロファイル欠落時は INCOMPLETE（サイレント PASS 禁止）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .findings import Finding, Status, Severity


@dataclass
class GenericVariable:
    name: str
    source_column: str
    numeric_map: dict = field(default_factory=dict)  # 生値キー(str/int) -> 数値 or None
    treat_as_missing: list = field(default_factory=list)  # 生値(int/float/str)のリスト


def load_generic_codebook(path: str) -> list[GenericVariable]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out: list[GenericVariable] = []
    for v in data["variables"]:
        out.append(
            GenericVariable(
                name=v["name"],
                source_column=v["source_column"],
                numeric_map=dict(v.get("numeric_map", {})),
                treat_as_missing=list(v.get("treat_as_missing", [])),
            )
        )
    return out


def _canon(v):
    """生値の正準化（pipeline.schemas._canon_raw_value と同一規則）。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return int(f) if f.is_integer() else f
    s = str(v).strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return s.casefold()


def _canon_set(values) -> set:
    return {_canon(v) for v in values}


def check_a_generic(variables: list[GenericVariable], data_profile: dict | None = None,
                    user_dictionary: dict | None = None) -> list[Finding]:
    """generic codebook を data_profile／ユーザー辞書と突合する。

    信頼順位: ユーザー辞書（authoritative） > プロファイル候補（ヒューリスティック）。
    両方欠落なら INCOMPLETE（既存 check_a の辞書引き失敗と同格）。

    Fix1: 辞書が明示的に宣言する `missing_codes`（authoritative）は、たとえ同じ値が
    `allowed_values` にも重複掲載されていても、絶対に missing 集合から消えない。
    allowed_values による「正当化」が効くのはプロファイラ heuristic 候補に対してのみ。

    Fix2: センチネル候補の"根拠"が辞書（authoritative）かプロファイラ heuristic かで
    確定度合いが違うため、offender の重大度を分離する:
    - authoritative（辞書 missing_codes / allowed_values、または変数自身の
      treat_as_missing との自己矛盾）を根拠とする欠陥 → 確定的 Status.FAIL。
    - heuristic（プロファイラの sentinel_candidates のみ）を根拠とする欠陥
      → サイレント PASS にはしないが、確定的欠陥ではないため Status.INCOMPLETE
      （人間レビューへ）。Fable C1（見逃し）と Codex #10（過検出ハード FAIL）の両立。
    """
    findings: list[Finding] = []
    columns = (data_profile or {}).get("columns", {})
    user_dictionary = user_dictionary or {}

    for v in variables:
        col = columns.get(v.source_column)
        entry = user_dictionary.get(v.source_column)
        if col is None and entry is None:
            findings.append(
                Finding("A", Status.INCOMPLETE, Severity.CRITICAL,
                        f"一次ソース(プロファイル/辞書)に列が見つからず監査不能: {v.name}",
                        f"source_column={v.source_column}", variable=v.name)
            )
            continue

        # authoritative_missing（辞書 missing_codes）は何があっても消えない（Fix1）。
        authoritative_missing: set = set()
        if entry:
            authoritative_missing |= _canon_set(entry.get("missing_codes", []))

        heuristic_missing: set = set()
        if col:
            sc = col.get("sentinel_candidates", {})
            heuristic_missing |= _canon_set(sc.get("numeric", []))
            heuristic_missing |= _canon_set(sc.get("tokens", []))

        declared = _canon_set(v.treat_as_missing)

        canon_map: dict = {}
        for raw_key, val in v.numeric_map.items():
            canon_map[_canon(raw_key)] = (raw_key, val)

        # 列ドメイン（辞書 allowed_values 優先=authoritative、無ければ観測 distinct 値=非authoritative）。
        # authoritative フラグは (ii) out-of-domain 判定の発火条件として使う: 観測値は「存在」の
        # 証拠であって「不在の無効性」の証拠ではないため、辞書が無いドメインでの recode 拒否は不健全。
        domain: set | None = None
        domain_authoritative = False
        if entry and entry.get("allowed_values") is not None:
            domain = _canon_set(entry["allowed_values"])
            domain_authoritative = True
            # allowed_values による正当化は heuristic 候補のみに効く（Fix1）:
            # 辞書が明示的に missing_codes 宣言した値は、allowed_values に重複掲載
            # されていても絶対に除去しない（900のような取り違えを見逃さない）。
            heuristic_missing -= domain
        elif col and col.get("distinct_values") is not None:
            domain = _canon_set(col["distinct_values"])

        missing = authoritative_missing | heuristic_missing

        authoritative_offenders: list[str] = []
        heuristic_offenders: list[str] = []

        for ck in sorted(canon_map, key=repr):
            raw_key, val = canon_map[ck]
            if ck in declared and val is not None:
                # 変数自身の treat_as_missing 宣言との自己矛盾＝根拠は宣言そのもの、常に確定的。
                authoritative_offenders.append(
                    f"[欠損宣言と矛盾] {v.source_column} value='{raw_key}' に {val} を割当")
            elif ck in missing and ck not in declared and val is not None:
                label = (f"[センチネル/欠損コード混入] {v.source_column} "
                         f"value='{raw_key}' に {val} を割当")
                if ck in authoritative_missing:
                    authoritative_offenders.append(label)
                else:
                    heuristic_offenders.append(label)
            elif (domain_authoritative and domain is not None and ck not in domain
                    and ck not in missing and ck not in declared):
                # domain_authoritative は辞書 allowed_values 由来なので常に確定的。
                authoritative_offenders.append(
                    f"[列ドメイン外recode] {v.source_column} value='{raw_key}' はドメインに存在しない")

        # 未処理センチネル（map にも宣言にも現れない）。passthrough 変数はここが生命線:
        # 連続ラボ値の 999 がそのまま解析に流れるケース（fail-closed、サイレント PASS 禁止）。
        for m in sorted(missing - declared - set(canon_map), key=repr):
            label = f"[センチネル未宣言] {v.source_column} 候補値 '{m}' が treat_as_missing に無い"
            if m in authoritative_missing:
                authoritative_offenders.append(label)
            else:
                heuristic_offenders.append(label)

        if authoritative_offenders:
            findings.append(
                Finding("A", Status.FAIL, Severity.CRITICAL,
                        f"センチネル/欠損コード処理に欠陥: {v.name}",
                        "; ".join(authoritative_offenders + heuristic_offenders), variable=v.name)
            )
        elif heuristic_offenders:
            findings.append(
                Finding("A", Status.INCOMPLETE, Severity.CRITICAL,
                        f"ヒューリスティック候補センチネルの扱いが未確認（人間レビュー要）: {v.name}",
                        "; ".join(heuristic_offenders), variable=v.name)
            )
        else:
            findings.append(
                Finding("A", Status.PASS, Severity.CRITICAL,
                        f"センチネル/欠損コード処理は妥当: {v.name}",
                        f"{v.source_column} センチネル={sorted(missing, key=repr)}",
                        variable=v.name)
            )
    return findings
