from __future__ import annotations

from enum import Enum

from audit.tier1.findings import Status
from .matrix import _family
from .verdict import Verdict


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ESCALATE_HUMAN = "escalate_human"
    UNRESOLVED = "unresolved"


# デデュープ時の悪化順位（フェイルクローズ: 同一モデルが複数評決を返したら最悪を採用）。
_WORST_FIRST = {Status.FAIL: 0, Status.INCOMPLETE: 1, Status.PASS: 2}


def aggregate_finding(verdicts: list[Verdict], critical: bool) -> Outcome:
    if not verdicts:
        return Outcome.ESCALATE_HUMAN
    if critical:
        # モデル単位でデデュープ（最悪ステータス優先）。単一外部PASSでは critical を
        # 承認できない: >=2 の DISTINCT ファミリからの PASS を要求する（quorum, Fix B）。
        dedup: dict[str, Verdict] = {}
        for v in verdicts:
            cur = dedup.get(v.model)
            if cur is None or _WORST_FIRST[v.status] < _WORST_FIRST[cur.status]:
                dedup[v.model] = v
        uniq = list(dedup.values())
        if any(v.status in (Status.FAIL, Status.INCOMPLETE) for v in uniq):
            return Outcome.ESCALATE_HUMAN
        families = {_family(v.model) for v in uniq}  # 残りは全て PASS
        if len(families) >= 2:
            return Outcome.PASS
        return Outcome.ESCALATE_HUMAN
    if any(v.status is Status.INCOMPLETE for v in verdicts):
        return Outcome.UNRESOLVED
    n_fail = sum(1 for v in verdicts if v.status is Status.FAIL)
    n_pass = sum(1 for v in verdicts if v.status is Status.PASS)
    if n_fail > n_pass:
        return Outcome.FAIL
    if n_pass > n_fail:
        return Outcome.PASS
    return Outcome.UNRESOLVED
