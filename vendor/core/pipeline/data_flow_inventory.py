from __future__ import annotations

import json
import os
from datetime import datetime, timezone

INVENTORY_FILENAME = "data_flow_inventory.jsonl"

REQUIRED_FIELDS = (
    "recipient",       # e.g. "codex", "gemini", "fable" (config.yaml role/model name)
    "data_description",  # what was sent: "full manuscript + primary-source CSV rows", etc.
    "individual_level",  # bool: does the payload contain row-level / participant-level data?
    "handling_terms",  # contract/retention basis, e.g. "API, zero-retention per vendor DPA"
    "purpose",          # which audit/agent stage this call served
)


class DataFlowInventoryError(Exception):
    pass


def record_data_flow(entries: list[dict], stage_dir: str, run_id: str | None = None) -> str:
    """Append one line per external-model call that could have received
    individual-level survey data, to a durable, append-only inventory.

    Added 2026-07-28 in response to external review: no mechanism previously
    tracked which AI model received which individual-level data, under what
    contract/retention terms. Tier2/Tier3 external audit models (codex,
    gemini, fable per config.yaml audit_role_fallbacks) can receive "all
    artifacts + primary sources" (DESIGN references), which for this project
    includes row-level JASTIS/JACSIS survey data; that data flow must be
    auditable independent of whether the recipient's response was useful.

    Each entry must contain all of REQUIRED_FIELDS. Entries are appended
    (never overwritten) with a UTC timestamp, so the inventory accumulates
    across a run and across re-runs; callers needing "since panel entry"
    history should read the full file, not assume the latest write is
    complete.
    """
    for e in entries:
        missing = [f for f in REQUIRED_FIELDS if f not in e]
        if missing:
            raise DataFlowInventoryError(
                f"data-flow inventory entry missing required field(s) {missing}: {e}"
            )
    path = os.path.join(stage_dir, INVENTORY_FILENAME)
    with open(path, "a", encoding="utf-8") as fh:
        for e in entries:
            record = dict(e)
            record["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
            record["run_id"] = run_id
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_data_flow(stage_dir: str) -> list[dict]:
    path = os.path.join(stage_dir, INVENTORY_FILENAME)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
