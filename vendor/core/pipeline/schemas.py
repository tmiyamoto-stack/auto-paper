from __future__ import annotations

import math


def _is_str(x) -> bool:
    return isinstance(x, str)


def _is_real_number(x) -> bool:
    """有限の実数値か（Python bool と NaN/Inf を拒否）。Fix I。"""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_variable_codebook(obj) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict) or not isinstance(obj.get("variables"), list):
        return ["variable_codebook: top-level must be {'variables': [...]}"]
    for i, v in enumerate(obj["variables"]):
        if not isinstance(v, dict):
            errs.append(f"variables[{i}]: must be object")
            continue
        for key in ("name", "survey", "source_question_code"):
            if not _is_str(v.get(key)):
                errs.append(f"variables[{i}]: missing/invalid '{key}'")
        nm = v.get("numeric_map", {})
        if not isinstance(nm, dict):
            errs.append(f"variables[{i}].numeric_map: must be object")
        else:
            # Track ordinals for duplicate detection after int coercion
            ordinal_to_keys: dict[int, list[str]] = {}
            for k, val in nm.items():
                try:
                    int_k = int(k)
                    if int_k not in ordinal_to_keys:
                        ordinal_to_keys[int_k] = []
                    ordinal_to_keys[int_k].append(k)
                except (TypeError, ValueError):
                    errs.append(f"variables[{i}].numeric_map: key '{k}' not int-coercible")
                if val is not None and not _is_real_number(val):
                    errs.append(f"variables[{i}].numeric_map['{k}']: value must be finite number or null")

            # Check for post-coercion duplicate ordinals
            for int_ord in sorted(ordinal_to_keys.keys()):
                keys = ordinal_to_keys[int_ord]
                if len(keys) > 1:
                    errs.append(f"variables[{i}].numeric_map: duplicate ordinal {int_ord} from keys {keys}")

        tm = v.get("treat_as_missing", [])
        if not isinstance(tm, list) or any(
            isinstance(x, bool) or not isinstance(x, int) for x in tm
        ):
            errs.append(f"variables[{i}].treat_as_missing: must be list of ints")
    return errs


def _canon_raw_value(v):
    """generic codebook の生値キー/欠損宣言の正準化。

    数値文字列は数値へ（"999" ≡ 999 ≡ 999.0、整数化可能な float は int へ）、
    文字列トークンは strip＋casefold（DESIGN_generic_clinical §4.4）。
    """
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


def validate_generic_codebook(obj) -> list[str]:
    """generic（臨床）プロファイル用 codebook バリデータ。

    既存 `validate_variable_codebook`（survey/source_question_code 依存）とは並置であり、
    そちらの契約には一切触れない。スキーマは DESIGN_generic_clinical.md §5。
    """
    errs: list[str] = []
    if not isinstance(obj, dict) or not isinstance(obj.get("variables"), list):
        return ["generic_codebook: top-level must be {'variables': [...]}"]
    for i, v in enumerate(obj["variables"]):
        if not isinstance(v, dict):
            errs.append(f"variables[{i}]: must be object")
            continue
        for key in ("name", "source_column"):
            if not _is_str(v.get(key)):
                errs.append(f"variables[{i}]: missing/invalid '{key}'")
        nm = v.get("numeric_map", {})
        if not isinstance(nm, dict):
            errs.append(f"variables[{i}].numeric_map: must be object")
        else:
            canon_to_keys: dict = {}
            for k, val in nm.items():
                canon_to_keys.setdefault(_canon_raw_value(k), []).append(k)
                if val is not None and not _is_real_number(val):
                    errs.append(f"variables[{i}].numeric_map['{k}']: value must be finite number or null")
            for canon in sorted(canon_to_keys, key=repr):
                keys = canon_to_keys[canon]
                if len(keys) > 1:
                    errs.append(f"variables[{i}].numeric_map: duplicate canonical key {canon!r} from keys {keys}")
        tm = v.get("treat_as_missing", [])
        if not isinstance(tm, list) or any(
            isinstance(x, bool)
            or not isinstance(x, (int, float, str))
            or (isinstance(x, (int, float)) and not math.isfinite(x))
            for x in tm
        ):
            errs.append(f"variables[{i}].treat_as_missing: must be list of finite scalars (int/float/str)")
    return errs


def _validate_wave_records(obj, required_keys, label) -> list[str]:
    """methods_claims / code_filters の共通バリデータ。

    Fix G: vacuous scope（check_b の空虚 PASS を可能にする穴）を schema-invalid にする。
    - applies_to が空リスト → 無効（適用対象ゼロの主張/フィルタは検証を素通りする）。
    - id の重複 → 無効（同一 id で証跡が上書き/衝突する）。
    - evidence が空文字列 → 無効（根拠の無いコードフィルタ）。
    """
    errs: list[str] = []
    if not isinstance(obj, list):
        return [f"{label}: must be a list"]
    seen_ids: dict[str, int] = {}
    for i, r in enumerate(obj):
        if not isinstance(r, dict):
            errs.append(f"{label}[{i}]: must be object")
            continue
        for key in required_keys:
            if key == "applies_to":
                av = r.get("applies_to")
                if not isinstance(av, list) or any(not _is_str(w) for w in (av if isinstance(av, list) else [])):
                    errs.append(f"{label}[{i}].applies_to: must be list[str]")
                elif len(av) == 0:
                    errs.append(f"{label}[{i}].applies_to: must be non-empty")
            elif key == "evidence":
                ev = r.get("evidence")
                if not _is_str(ev):
                    errs.append(f"{label}[{i}]: missing/invalid 'evidence'")
                elif ev.strip() == "":
                    errs.append(f"{label}[{i}].evidence: must be non-empty")
            elif not _is_str(r.get(key)):
                errs.append(f"{label}[{i}]: missing/invalid '{key}'")
        if "id" in required_keys:
            rid = r.get("id")
            if _is_str(rid):
                if rid in seen_ids:
                    errs.append(f"{label}: duplicate id '{rid}' (indices {seen_ids[rid]}, {i})")
                else:
                    seen_ids[rid] = i
    return errs


def validate_methods_claims(obj) -> list[str]:
    return _validate_wave_records(obj, ("id", "procedure", "applies_to"), "methods_claims")


def validate_code_filters(obj) -> list[str]:
    return _validate_wave_records(obj, ("procedure", "applies_to", "evidence"), "code_filters")


def validate_results(obj) -> list[str]:
    if not isinstance(obj, dict):
        return ["results: top-level must be an object"]
    return []


def validate_flow(obj) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict) or not isinstance(obj.get("stages"), list):
        return ["flow: top-level must be {'stages': [...]}"]
    prev = None
    for i, s in enumerate(obj["stages"]):
        n = s.get("n") if isinstance(s, dict) else None
        # Fix I: n は真の int のみ（bool は int 派生だが N ではない）。
        if not isinstance(s, dict) or not _is_str(s.get("label")) or not isinstance(n, int) or isinstance(n, bool):
            errs.append(f"flow.stages[{i}]: must have str label and int n")
            continue
        if prev is not None and s["n"] > prev:
            errs.append(f"flow.stages[{i}]: N increased ({prev}->{s['n']}); must be non-increasing")
        prev = s["n"]
    return errs
