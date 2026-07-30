from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Status(str, Enum):
    FAIL = "fail"
    PASS = "pass"
    INCOMPLETE = "incomplete"


@dataclass
class Finding:
    """監査所見。

    `check_id` は既存の一文字 ID（凍結・後方互換）。`rule_id`/`taxonomy_id` は
    `audit.tier1.registry` の三層名前空間への追加フィールドで、いずれも**末尾
    デフォルト付きの純加算**である（既存の位置引数呼び出しを一切壊さない）。
    名前空間の設計意図はレジストリの docstring を参照。
    """

    check_id: str
    status: Status
    severity: Severity
    summary: str
    evidence: str
    variable: str | None = None
    rule_id: str | None = None
    taxonomy_id: str | None = None


@dataclass
class CoverageProof:
    check_id: str
    files_read: list[tuple[str, str]] = field(default_factory=list)
    items_checked: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    rule_id: str | None = None
    taxonomy_id: str | None = None
