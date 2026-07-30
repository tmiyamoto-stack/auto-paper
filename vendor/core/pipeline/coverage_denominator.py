from __future__ import annotations

import re

"""External coverage denominators.

Added 2026-07-28 in response to external review: DESIGN.md section 4.1.2's
four counts (available/required/executed/complete) are a real improvement
over a single "N checks passed" number, but their denominator is still the
generation side's own self-reported list of items (methods_claims.json,
code_filters.json, the `refs` list an audit script builds). If that
self-reported list is itself incomplete -- exactly what happened when
audit_econ_v4.py's regex only added DOI-bearing references to `refs`,
silently making the 2 DOI-less references invisible to check_m -- the
four counts still look clean.

This module computes denominators independently, by parsing the manuscript
text itself rather than trusting any list the audit script assembled. It is
deliberately narrow in scope: citation coverage is the one category where an
external denominator can be extracted reliably by regex (a numbered
bibliography plus in-text [n] markers). Extending this to "every claim" or
"every variable" would require semantic parsing this module does not
attempt; DESIGN.md section 11.2 records that as unimplemented.
"""

_BIB_ENTRY_RE = re.compile(r"^(\d+)\.\s+\S", re.M)
_INTEXT_CITE_RE = re.compile(r"\[(\d+(?:\s*[,\-]\s*\d+)*)\]")


def extract_cited_reference_ids(manuscript_text: str) -> set[str]:
    """All reference numbers that exist in the manuscript: every numbered
    bibliography entry, unioned with every number appearing in an in-text
    citation marker like [12] or [3,4] or [7-9] (ranges expanded). This is
    the external denominator -- it does not depend on any list an audit
    script built.
    """
    ids = set(_BIB_ENTRY_RE.findall(manuscript_text))
    for group in _INTEXT_CITE_RE.findall(manuscript_text):
        for part in re.split(r"\s*,\s*", group):
            if "-" in part:
                lo, hi = part.split("-", 1)
                if lo.strip().isdigit() and hi.strip().isdigit():
                    ids.update(str(n) for n in range(int(lo), int(hi) + 1))
            elif part.strip().isdigit():
                ids.add(part.strip())
    return ids


def citation_coverage(manuscript_text: str, checked_ref_ids) -> dict:
    """Compare the audit's self-reported checked-reference list against the
    externally (regex-)extracted denominator.

    checked_ref_ids: iterable of ids as used by the audit script, e.g.
    "ref12" (audit_econ_v4.py's convention) or "12" -- both accepted, the
    leading "ref" prefix is stripped for comparison.
    """
    all_refs = extract_cited_reference_ids(manuscript_text)
    checked = {str(r).replace("ref", "") for r in checked_ref_ids}
    checked_in_manuscript = all_refs & checked
    missing = all_refs - checked
    return {
        "denominator_source": "manuscript (numbered bibliography + in-text [n] markers), independent of audit self-report",
        "n_total_in_manuscript": len(all_refs),
        "n_checked": len(checked_in_manuscript),
        "n_missing_from_audit": len(missing),
        "missing_ref_ids": sorted(missing, key=lambda x: int(x) if x.isdigit() else 10**9),
        "coverage_ratio": round(len(checked_in_manuscript) / len(all_refs), 3) if all_refs else None,
    }
