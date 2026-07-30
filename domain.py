# -*- coding: utf-8 -*-
"""ドメイン参照パックの読み込みと、監査コアへ渡す引数の組み立て。

## なぜ「ドメイン」がチェック集合を選ばないのか

素朴には「臨床ドメインなら値域チェックを有効、汎用なら無効」にしたくなるが、
それは誤りである。値域外れ値（check D）・単位混在（check U）・打ち切り
（check L）・不死時間バイアス（check I）はいずれも**臨床固有の概念ではない**。

  - 「ありえない値」は業務データにも普通にある（負の売上、在庫 -1、年齢 999）。
  - 単位混在は経済データの方が深刻（円/千円/百万円、名目/実質）。
  - 打ち切りは所得のトップコーディングで日常的に起きる。
  - 不死時間バイアスは「曝露が確定する前の期間を追跡に含める」設計上の誤りで、
    縦断データであればドメインを問わず成立する。

臨床固有なのはチェックの**ロジック**ではなく**参照データ**（生理的値域・単位換算表）
だけである。したがって本スキルは:

  - チェック集合は全ドメインで同一（コアの `run_tier1_generic` をそのまま使う）
  - ドメインは**参照データのパック**を選ぶだけ

とする。参照データが供給されない変数について、コアは PASS を出さず INCOMPLETE を
返す（`check_d` は `ranges` に無い変数を単に飛ばすため、飛ばした事実を本モジュールが
明示的に surface する）。「臨床じゃないから値域は見ない」という運用に落ちないための設計。

## SAP 宣言の優先順位

  研究ごとの SAP 宣言（工程1） ＞ ドメインパックの既定値

パックは出発点を与えるだけで、authoritative ではない。
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOMAINS_DIR = os.path.join(HERE, "references", "domains")

KNOWN_DOMAINS = ("clinical", "survey", "general")


class DomainError(ValueError):
    """ドメイン指定が不正、またはパックを読めない。"""


def available_domains() -> list[str]:
    if not os.path.isdir(DOMAINS_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0] for f in os.listdir(DOMAINS_DIR) if f.endswith(".json")
    )


def load_pack(domain: str | None) -> dict:
    """ドメインパックを読む。

    `domain` が None／未知の場合は例外にする（暗黙に general へ倒さない）。
    ドメイン未宣言のまま監査を通すと「参照データが無いので何も照合しなかった」
    ことに気づけないため、宣言を強制する。
    """
    if not domain:
        raise DomainError(
            "domain が宣言されていない。"
            f"次のいずれかを指定すること: {', '.join(available_domains()) or '(パック無し)'}。"
            "ドメインは参照データ（値域・単位の基準）の選択にのみ用いられ、"
            "チェック集合は全ドメインで同一である。"
        )
    path = os.path.join(DOMAINS_DIR, f"{domain}.json")
    if not os.path.exists(path):
        raise DomainError(
            f"未知の domain '{domain}'。利用可能: {', '.join(available_domains()) or '(なし)'}"
        )
    with open(path, encoding="utf-8") as fh:
        pack = json.load(fh)
    for key in ("impossible_ranges", "plausible_ranges", "plausible_by_unit"):
        pack.setdefault(key, {})
    return pack


def _as_ranges(d: dict) -> dict:
    """JSON の [lo, hi] を check_d が期待する tuple に変換する。

    形式だけでなく**中身**も検証する。lo > hi の逆転範囲は全観測値を範囲外に
    してしまい、文字列や NaN は比較時に例外か無意味な判定になる。いずれも
    「監査が意味を失ったまま走る」ため、入力検証の失敗として止める。
    """
    out = {}
    for k, v in d.items():
        if not (isinstance(v, (list, tuple)) and len(v) == 2):
            raise DomainError(f"値域の形式が不正: {k} -> {v!r}（[lo, hi] であること）")
        lo, hi = v
        for label, x in (("lo", lo), ("hi", hi)):
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise DomainError(f"値域 {k} の {label} が数値でない: {x!r}")
            if x != x or x in (float("inf"), float("-inf")):   # NaN / ±inf
                raise DomainError(f"値域 {k} の {label} が有限数でない: {x!r}")
        if lo > hi:
            raise DomainError(
                f"値域 {k} の下限が上限を超えている: [{lo}, {hi}]。"
                "全観測値が範囲外と判定され監査が無意味になるため中止する。")
        out[k] = (lo, hi)
    return out


def merge_ranges(pack: dict, sap_declared: dict | None, key: str) -> dict:
    """パック既定値に SAP 宣言を重ねる（SAP が勝つ）。"""
    merged = dict(_as_ranges(pack.get(key, {})))
    if sap_declared:
        merged.update(_as_ranges(sap_declared))
    return merged


def build_audit_kwargs(domain: str,
                       observed: dict | None = None,
                       sap_impossible_ranges: dict | None = None,
                       sap_plausible_ranges: dict | None = None,
                       declared_units: dict | None = None,
                       sap_plausible_by_unit: dict | None = None) -> dict:
    """`run_tier1_generic` に渡す値域・単位関連の引数を組み立てる。

    返り値は `outlier_ranges` / `impossible_ranges` / `unit_plausible` などの
    キーワード引数辞書。`observed` を渡すと、参照値域を持たない観測変数を
    `unranged_variables` として報告する（呼び出し側が surface するため）。
    """
    pack = load_pack(domain)
    plausible = merge_ranges(pack, sap_plausible_ranges, "plausible_ranges")
    impossible = merge_ranges(pack, sap_impossible_ranges, "impossible_ranges")
    unit_plausible = dict(_as_ranges(pack.get("plausible_by_unit", {})))
    if sap_plausible_by_unit:
        unit_plausible.update(_as_ranges(sap_plausible_by_unit))

    unranged: list[str] = []
    if observed:
        unranged = sorted(k for k in observed if k not in plausible and k not in impossible)

    return {
        "domain": pack["domain"],
        "outlier_ranges": plausible,
        "impossible_ranges": impossible,
        "unit_plausible": unit_plausible,
        "declared_units": dict(declared_units or {}),
        # check_d は ranges に無い変数を黙って飛ばす。飛ばした列を明示して
        # 「値域未宣言のまま監査を通した」ことに気づけるようにする。
        "unranged_variables": unranged,
    }


def unranged_warning(kwargs: dict) -> str | None:
    """値域未宣言の観測変数があれば、人間に見せる警告文を返す。"""
    unranged = kwargs.get("unranged_variables") or []
    if not unranged:
        return None
    return (
        f"[要確認] 値域が宣言されていない観測変数が {len(unranged)} 件あり、"
        f"check D はこれらを照合していない: {', '.join(unranged)}\n"
        "  ドメインが臨床でなくても『ありえない値』は存在する（負の売上・在庫 -1・年齢999）。"
        "SAP に impossible_ranges / plausible_ranges を宣言すれば、"
        "臨床と同じ強度で決定的に照合される。"
    )
