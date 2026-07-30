"""Check I（不死時間バイアスの構造化ガード）。

コホート日付列（`index_date`＝組入れ, `exposure_date`＝曝露確定日/未曝露は None,
`followup_start`＝追跡開始, `outcome_date`＝イベント/無イベントは None）の時間順序を
決定的に照合する（DESIGN §9）。時間固定曝露デザインで、曝露が確定するより前から
追跡person-timeを計上すると、その区間は構造的にイベントが起きえない「不死時間」に
なり、曝露群の見かけの生存を過大評価する（immortal time bias）。

Finding 契約は check_d/check_k/check_l と同一（check_id="I", CRITICAL, 決定的・sorted）。

規則:
- 時間妥当性（exposure_type によらず常時）: exposure_date<index_date /
  followup_start<index_date / outcome_date<followup_start は各々データ矛盾 → FAIL。
- 不死時間（exposure_type=="time_fixed" のみ）: 曝露被験者で
  followup_start<exposure_date → 曝露確定前の追跡計上 → FAIL。
  time-varying/landmark は正しいデザインなので発火しない。
- 不死アウトカム（exposure_type=="time_fixed" のみ）: 曝露被験者で
  index_date<=outcome_date<exposure_date → 時間固定曝露では構造的に不可能 → FAIL。
- subjects 空、または index_date/followup_start が全被験者で欠損・解析不能 →
  INCOMPLETE（監査不能、サイレント PASS 禁止）。
"""
from __future__ import annotations

from datetime import date

from .findings import Finding, Status, Severity

_VALID_EXPOSURE_TYPES = ("time_fixed", "time_varying", "landmark")


def _parse(value):
    """ISO 日付文字列 → (date|None, error:bool)。None 値はエラー扱いしない。"""
    if value is None:
        return None, False
    try:
        return date.fromisoformat(value), False
    except (ValueError, TypeError):
        return None, True


def check_i_immortal(subjects: list[dict], exposure_type: str) -> list[Finding]:
    if not subjects:
        return [Finding("I", Status.INCOMPLETE, Severity.CRITICAL,
            "不死時間監査不能: subjects が空", "subjects=0")]

    reasons: list[str] = []
    usable: list[tuple] = []  # (idx, index_date, exposure_date, followup_start, outcome_date)
    for i, s in enumerate(subjects):
        idx, e_idx = _parse(s.get("index_date"))
        fus, e_fus = _parse(s.get("followup_start"))
        exp, e_exp = _parse(s.get("exposure_date"))
        out, e_out = _parse(s.get("outcome_date"))
        if e_idx or s.get("index_date") is None:
            reasons.append(f"subject[{i}] index_date 欠損/解析不能")
        if e_fus or s.get("followup_start") is None:
            reasons.append(f"subject[{i}] followup_start 欠損/解析不能")
        if e_exp:
            reasons.append(f"subject[{i}] exposure_date 解析不能='{s.get('exposure_date')}'")
        if e_out:
            reasons.append(f"subject[{i}] outcome_date 解析不能='{s.get('outcome_date')}'")
        if idx is None or fus is None:
            continue
        usable.append((i, idx, exp, fus, out))

    if not usable:
        return [Finding("I", Status.INCOMPLETE, Severity.CRITICAL,
            "不死時間監査不能: index_date/followup_start が全被験者で欠損・解析不能",
            "; ".join(sorted(reasons)) or f"n={len(subjects)}")]

    exp_before_index: list[int] = []
    fus_before_index: list[int] = []
    out_before_fus: list[int] = []
    immortal_time: list[int] = []
    immortal_outcome: list[int] = []
    time_fixed = exposure_type == "time_fixed"
    for (i, idx, exp, fus, out) in usable:
        if exp is not None and exp < idx:
            exp_before_index.append(i)
        if fus < idx:
            fus_before_index.append(i)
        if out is not None and out < fus:
            out_before_fus.append(i)
        if time_fixed and exp is not None and fus < exp:
            immortal_time.append(i)
        if time_fixed and exp is not None and out is not None and idx <= out < exp:
            immortal_outcome.append(i)

    findings: list[Finding] = []

    def emit(offenders: list[int], summary: str) -> None:
        off = sorted(offenders)
        findings.append(Finding("I", Status.FAIL, Severity.CRITICAL, summary,
            f"件数={len(off)} 例=subjects{off[:2]}"))

    if exp_before_index:
        emit(exp_before_index, "曝露確定日が組入れ日より前=データ矛盾")
    if fus_before_index:
        emit(fus_before_index, "追跡開始が組入れ日より前=データ矛盾")
    if out_before_fus:
        emit(out_before_fus, "アウトカムが追跡開始より前=データ矛盾")
    if immortal_time:
        emit(immortal_time,
             "不死時間: 曝露確定前から追跡を計上。time-varying曝露かランドマーク解析が必要")
    if immortal_outcome:
        emit(immortal_outcome,
             "不死アウトカム: アウトカムが曝露確定前の不死区間に発生=時間固定曝露では構造的に不可能")

    if not findings:
        findings.append(Finding("I", Status.PASS, Severity.CRITICAL,
            "不死時間/時間順序の構造的違反なし",
            f"n={len(usable)} exposure_type={exposure_type}"))

    if reasons:
        findings.append(Finding("I", Status.INCOMPLETE, Severity.CRITICAL,
            "一部被験者の必須日付が欠損・解析不能（部分監査）",
            "; ".join(sorted(reasons))))
    return findings
