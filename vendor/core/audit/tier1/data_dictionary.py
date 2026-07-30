from __future__ import annotations

import csv
from dataclasses import dataclass

NON_RESPONSE_LABELS: set[str] = {"答えたくない", "分からない", "わからない", "無回答", "非該当"}


@dataclass(frozen=True)
class Choice:
    ordinal: int
    label: str


def _answer_id_seq(master_answer_id: str) -> int:
    # "JASTISQ0014-A19" -> 19（master_answer_id 内の連番。回答コードとは限らない）
    return int(master_answer_id.rsplit("-A", 1)[1])


# 後方互換のための別名（旧称で参照している呼び出しがあれば動く）。
_ordinal_from_answer_id = _answer_id_seq


class AmbiguousQuestionCode(Exception):
    """設問コードが波をまたいで別の意味で再利用されており、波を指定せずに
    選択肢を確定できない（サイレントに混ぜてはならない）。

    JASTIS では実際に `Q10` が2021–2025の全波に存在し、うち4通りの異なる選択肢集合を
    持つ（2021年は世帯収入20択、他年は別設問）。波を指定せず読むと、異なる波のラベルが
    同一 ordinal に重なって上書きされ、非回答 ordinal の集合も和集合になる。その結果、
    当該波には存在しない非回答コードを検出したり（偽陽性）、逆に取り違えた設問の
    ラベルで PASS を出したり（偽陰性）する。決定的照合の前提が壊れるため、
    曖昧なまま照合を続けず fail-closed で停止する。
    """


def load_choices(csv_path: str, survey: str, question_code: str,
                 year: str | None = None) -> list[Choice]:
    """一次ソース辞書から選択肢を読む。

    `year` を指定するとその波に限定する。指定しない場合、当該 question_code が
    複数の波で**異なる選択肢集合**を持つときは `AmbiguousQuestionCode` を送出する
    （単一波しか無い、または全波で選択肢集合が同一なら従来どおり返す）。
    """
    raw_by_year: dict[str, list[tuple[int, str]]] = {}
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("survey") != survey or row.get("question_code") != question_code:
                continue
            if year is not None and str(row.get("year")) != str(year):
                continue
            raw_by_year.setdefault(str(row.get("year")), []).append(
                (_answer_id_seq(row["master_answer_id"]), row["label"].strip()))

    # 回答コードは **辞書 CSV 内の出現順**（＝調査票の選択肢の並び順）で決まる。
    # master_answer_id の連番を回答コードとして使ってはならない。実データでは
    #   - JASTIS 2023 学歴 Q14.1 は A04〜A14（基点が1でない）
    #   - JASTIS 2025 禁煙試行 Q59 は A18/A19（はい=1/いいえ=2 のはず）
    #   - JASTIS 2025 学歴 Q11 は A10,A11,…,A18,A09,A32 と**並び順すら一致しない**
    #     （「その他」=A09 だが選択肢としては10番目、「分からない」=A32 だが11番目）
    # のように、連番は設問ごとに任意の基点・任意の順序で振られている。連番から回答
    # コードを導くと codebook のキーと系統的にずれ、非回答コードの照合が無効化される
    # （サイレントな偽陰性）。出現順は上記いずれの設問でも調査票の並びと一致していた。
    by_year: dict[str, list[Choice]] = {}
    for y, items in raw_by_year.items():
        by_year[y] = [Choice(i, label) for i, (_seq, label) in enumerate(items, start=1)]

    if not by_year:
        return []
    if len(by_year) > 1:
        signatures = {tuple((c.ordinal, c.label) for c in chs) for chs in by_year.values()}
        if len(signatures) > 1:
            raise AmbiguousQuestionCode(
                f"survey={survey} question_code={question_code} は "
                f"{sorted(by_year)} の各波で異なる選択肢集合を持つ"
                f"（{len(signatures)}通り）。codebook に year を指定すること")
    # 全波で同一（またはハーモナイズ済み）なので任意の波の集合を返す。
    return by_year[sorted(by_year)[0]]


def non_response_ordinals(choices: list[Choice], extra_labels: set[str] | None = None) -> set[int]:
    labels = NON_RESPONSE_LABELS | (extra_labels or set())
    return {c.ordinal for c in choices if c.label in labels}
