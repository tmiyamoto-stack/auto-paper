from __future__ import annotations

from audit.tier1.findings import CoverageProof


def coverage_gaps(coverage: list[CoverageProof], required_check_ids: set[str]) -> list[str]:
    gaps: list[str] = []
    present = {c.check_id for c in coverage}
    for c in coverage:
        for item in c.incomplete:
            gaps.append(f"{c.check_id}: INCOMPLETE item '{item}'")
        if (
            c.check_id in required_check_ids
            and not c.items_checked
            and not c.incomplete
        ):
            gaps.append(f"{c.check_id}: coverage proof examined nothing (vacuous)")
    for cid in required_check_ids - present:
        gaps.append(f"required check '{cid}' has no coverage proof")
    return sorted(gaps)


def blocks_acceptance(gaps: list[str]) -> bool:
    return bool(gaps)
