from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class DerivedVariable:
    name: str
    survey: str
    source_question_code: str
    numeric_map: dict[int, float | None] = field(default_factory=dict)
    treat_as_missing: list[int] = field(default_factory=list)
    # 設問コードが波をまたいで再利用される調査（JASTIS の Q10 等）で照合波を確定する。
    # None の場合、複数波で選択肢集合が異なると check A は fail-closed で INCOMPLETE。
    year: str | None = None


def load_codebook(path: str) -> list[DerivedVariable]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out: list[DerivedVariable] = []
    for v in data["variables"]:
        numeric_map = {int(k): val for k, val in v.get("numeric_map", {}).items()}
        out.append(
            DerivedVariable(
                name=v["name"],
                survey=v["survey"],
                source_question_code=v["source_question_code"],
                numeric_map=numeric_map,
                treat_as_missing=[int(x) for x in v.get("treat_as_missing", [])],
                year=(str(v["year"]) if v.get("year") is not None else None),
            )
        )
    return out
