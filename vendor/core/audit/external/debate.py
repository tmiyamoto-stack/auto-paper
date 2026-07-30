from __future__ import annotations

from .aggregate import Outcome, aggregate_finding
from .verdict import Verdict


def _summary(verdicts: list[Verdict]) -> str:
    return ", ".join(sorted(f"{v.model}:{v.status.value}" for v in verdicts))


def adjudicate(verdicts: list[Verdict], critical: bool) -> tuple[Outcome, str]:
    outcome = aggregate_finding(verdicts, critical)
    summ = _summary(verdicts)
    if critical and outcome is Outcome.ESCALATE_HUMAN:
        return outcome, f"クリティカル: FAIL/INCOMPLETEは統括が覆せない。人間直行。verdicts=[{summ}]"
    if not critical and outcome is Outcome.UNRESOLVED:
        return Outcome.FAIL, f"非クリティカルの割れ: 偽陰性コスト優先でFAIL側採用。verdicts=[{summ}]"
    return outcome, f"集約結果={outcome.value}。verdicts=[{summ}]"
