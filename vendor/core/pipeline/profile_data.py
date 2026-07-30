"""自動データプロファイラ（generic プロファイルの一次ソース生成）。

患者レベル表形式 CSV の各列から 型・観測 min/max・distinct 値（低カーディナリティ時）・
センチネル/欠損コード候補・カーディナリティ を推定し、`data_profile.json` 相当の
dict を返す。純関数・標準ライブラリのみ・決定的（set 由来は sorted）。

設計: references/DESIGN_generic_clinical.md §4（臨床センチネル方針）。
"""
from __future__ import annotations

import csv
import re

# --- センチネル定数（DESIGN §4.1） ---

CANONICAL_POSITIVE_SENTINELS: frozenset[int] = frozenset(
    {7, 8, 9, 66, 77, 88, 99, 666, 777, 888, 999,
     6666, 7777, 8888, 9999, 77777, 88888, 99999, 999999}
)
CANONICAL_NEGATIVE_SENTINELS: frozenset[int] = frozenset(
    set(range(-9, 0)) | {-66, -77, -88, -99, -666, -777, -888, -999,
                         -7777, -8888, -9999, -99999}
)
MISSING_TOKENS: frozenset[str] = frozenset(
    {"na", "n/a", "null", "none", "unknown", "missing", "refused", ".",
     "不明", "無回答", "答えたくない", "非該当", "わからない", "分からない", "欠損"}
)
# 打ち切り値/検出限界トークン（DESIGN §9、Part1a）。
# 検出限界未満の値は「欠測」ではなく「情報を持つ打ち切り観測」であり、
# MISSING_TOKENS とは別集合として追跡する（数値化して解析に流すと系統誤差）。
CENSORED_TOKENS: frozenset[str] = frozenset(
    {"検出せず", "検出限界未満", "検出限界以下", "定量下限未満", "nd", "not detected",
     "<lod", "<lloq", ">uln", "below detection limit"}
)
# 比較演算子接頭辞（"<5"、">1000"、"≤0.1"、"≥5" 等）。数値そのものではないが
# 打ち切り観測を表す。
_CENSORED_RE = re.compile(r"^\s*[<>≤≥]\s*-?\d")

# gap 規則の係数（DESIGN §4.2）
_EXTREME_GAP_FACTOR = 5.0
_EXTREME_MIN_COUNT = 3
_EXTREME_MIN_VALUE = 10

_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")


def _parse_number(s: str):
    """数値文字列を int（整数化可能なら）/ float に。数値でなければ None。"""
    try:
        return int(s)
    except ValueError:
        pass
    try:
        f = float(s)
    except ValueError:
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return int(f) if f.is_integer() else f


def _as_int_if_integral(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def sentinel_candidates_numeric(counts: dict) -> list:
    """数値 distinct 値→出現数 の dict からセンチネル候補を決定的に検出する。

    規則（DESIGN §4.2、Fix2 で改訂）:
    1. 定番正コード: 非定番最大値を「超える」定番コードは常に候補とする。旧規則は
       非定番最大値の 3 倍以上という gap ゲートで検出を抑制していたが、これは
       realistic な検査値域（例: 非定番最大値〜400）に 999 が混じるケースを見逃す
       systematic FN だった（Fable C1）。gap 係数は候補の強度づけに転用できる余地は
       残すが、検出そのものは抑制しない（Codex #10 の過検出ハードFAIL懸念は、
       ヒューリスティック候補の扱いを INCOMPLETE にする check_a_generic 側で吸収する）。
    2. 定番負コード: 非定番値が全て 0 以上のとき、定番負コードは候補。
    3. 高頻度極値: 定番剥がし後の最大値が count>=3 かつ >=10 かつ次点の 5 倍以上なら候補。
    """
    values = {}
    for k, c in counts.items():
        v = _as_int_if_integral(float(k))
        values[v] = values.get(v, 0) + int(c)
    if not values:
        return []

    non_canonical = [v for v in values
                     if v not in CANONICAL_POSITIVE_SENTINELS
                     and v not in CANONICAL_NEGATIVE_SENTINELS]
    candidates: set = set()

    # 1. 定番正コード（非定番最大値を超えていれば無条件に候補、Fix2）
    pos_canon = [v for v in values if isinstance(v, (int, float)) and v > 0
                 and v in CANONICAL_POSITIVE_SENTINELS]
    non_canon_max = max(non_canonical) if non_canonical else None
    if non_canon_max is not None:
        for v in pos_canon:
            if v > non_canon_max:
                candidates.add(v)

    # 2. 定番負コード（非定番値が全て非負のとき）
    if all(v >= 0 for v in non_canonical):
        for v in values:
            if v in CANONICAL_NEGATIVE_SENTINELS:
                candidates.add(v)

    # 3. 高頻度極値（非定番・反復・乖離）
    remaining = sorted(v for v in values if v not in candidates)
    if len(remaining) >= 2:
        top, second = remaining[-1], remaining[-2]
        if (values[top] >= _EXTREME_MIN_COUNT and top >= _EXTREME_MIN_VALUE
                and second > 0 and top >= _EXTREME_GAP_FACTOR * second):
            candidates.add(top)

    return sorted(candidates)


def _profile_column(raw_values: list[str], max_distinct: int) -> dict:
    n_empty = 0
    token_counts: dict[str, int] = {}
    censored_counts: dict[str, int] = {}
    numeric_counts: dict = {}
    parsed_distinct: set = set()
    typed: list[str] = []  # per-value type tags among non-empty non-token values

    for raw in raw_values:
        s = raw.strip() if isinstance(raw, str) else ("" if raw is None else str(raw))
        if s == "":
            n_empty += 1
            continue
        folded = s.casefold()
        num = _parse_number(s)
        # 打ち切り値/検出限界（Part1a）: 平文の数値ではないが比較演算子接頭辞または
        # 検出限界フレーズに一致するセル。欠測トークンより先に判定し、MISSING とは
        # 別集合として追跡する（"検出せず" は欠測ではなく打ち切り観測）。
        if num is None and (_CENSORED_RE.match(s) or folded in CENSORED_TOKENS):
            censored_counts[s] = censored_counts.get(s, 0) + 1
            parsed_distinct.add(s)
            continue
        if num is None and folded in MISSING_TOKENS:
            token_counts[folded] = token_counts.get(folded, 0) + 1
            parsed_distinct.add(s)
            continue
        if num is not None:
            numeric_counts[num] = numeric_counts.get(num, 0) + 1
            parsed_distinct.add(num)
            typed.append("integer" if isinstance(num, int) else "float")
        elif _DATE_RE.match(s):
            parsed_distinct.add(s)
            typed.append("date")
        else:
            parsed_distinct.add(s)
            typed.append("string")

    n_nonempty = len(raw_values) - n_empty
    kinds = set(typed)
    if not typed:
        col_type = "empty" if n_nonempty == 0 else "string"
    elif kinds <= {"integer"}:
        col_type = "integer"
    elif kinds <= {"integer", "float"}:
        col_type = "float"
    elif kinds == {"date"}:
        col_type = "date"
    elif kinds == {"string"}:
        col_type = "string"
    else:
        col_type = "mixed"

    numerics = sorted(numeric_counts)
    cardinality = len(parsed_distinct)
    if cardinality <= max_distinct:
        distinct_values = sorted(parsed_distinct, key=lambda v: (isinstance(v, str), v))
    else:
        distinct_values = None

    return {
        "type": col_type,
        "n_nonempty": n_nonempty,
        "n_empty": n_empty,
        "min": numerics[0] if numerics else None,
        "max": numerics[-1] if numerics else None,
        "cardinality": cardinality,
        "distinct_values": distinct_values,
        "sentinel_candidates": {
            "numeric": sentinel_candidates_numeric(numeric_counts),
            "tokens": sorted(token_counts),
        },
        "censored_candidates": sorted(censored_counts),
    }


def _normalize_header(name: str) -> str:
    return name.strip().casefold() if isinstance(name, str) else str(name)


def profile_rows(header: list[str], rows: list[list[str]], max_distinct: int = 20) -> dict:
    """ヘッダ＋行列（文字列セル）から data_profile dict を返す純関数。

    Fix4（Codex #11）: 重複ヘッダ名（正規化して同一視）はサイレントに上書きせず、
    `duplicate_headers`（sorted）としてプロファイルに記録する。クラッシュはしない
    （`columns` は従来通り最後の出現が勝つ）が、データ整合性ギャップとして下流に伝える。
    """
    seen: dict[str, int] = {}
    duplicate_headers: set[str] = set()
    for name in header:
        norm = _normalize_header(name)
        seen[norm] = seen.get(norm, 0) + 1
        if seen[norm] > 1:
            duplicate_headers.add(name)

    columns: dict[str, dict] = {}
    for idx, name in enumerate(header):
        raw_values = [row[idx] if idx < len(row) else "" for row in rows]
        columns[name] = _profile_column(raw_values, max_distinct)
    return {
        "n_rows": len(rows),
        "columns": columns,
        "duplicate_headers": sorted(duplicate_headers),
    }


def profile_csv(path: str, max_distinct: int = 20) -> dict:
    """CSV ファイルを読み `profile_rows` を適用する（1行目=ヘッダ）。"""
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return {"n_rows": 0, "columns": {}}
        rows = list(reader)
    return profile_rows(header, rows, max_distinct=max_distinct)
