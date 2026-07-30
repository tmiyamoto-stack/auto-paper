from __future__ import annotations

"""モデル横断の監査呼び出しレジストリ。

_CALLERS: モデル名 -> 呼び出し関数。codex は既存の codex_runner.run_codex_audit をそのまま登録し、
挙動を一切変えない。それ以外の既知モデル（gemini/opus/fable/local）は codex_runner と同じ
「注入 runner + JSON verdict 抽出（json.JSONDecoder.raw_decode）」契約に従う汎用呼び出しを使う。
未知モデルは常に INCOMPLETE/CRITICAL（サイレント PASS 禁止）。
"""

from audit.tier1.findings import Status, Severity
from .verdict import Verdict, validate_verdict, parse_verdict
from .codex_runner import run_codex_audit, _extract_json_objects


def _incomplete(model: str, finding_id: str, why: str) -> Verdict:
    return Verdict(model, finding_id, Status.INCOMPLETE, Severity.CRITICAL, f"{model} audit {why}")


def _generic_model_caller(model: str, prompt_path: str, artifact_path: str, finding_id: str, runner) -> Verdict:
    try:
        out = runner([model, prompt_path, artifact_path])
    except Exception as e:  # noqa: BLE001 - any runner failure -> unauditable
        return _incomplete(model, finding_id, f"runner error: {e}")

    candidates = _extract_json_objects(out or "")

    last_valid_verdict = None
    for candidate in candidates:
        if not validate_verdict(candidate):  # empty list is falsy, meaning valid
            last_valid_verdict = candidate

    if last_valid_verdict is None:
        return _incomplete(model, finding_id, "unparseable (no valid verdict)")

    verdict = parse_verdict(last_valid_verdict)
    # Fix C: モデルの自己申告 identity は信頼しない。実際に起動したモデル・要求 finding_id を
    # 権威として上書きし、blinded は必ず True（盲検はハーネスが担保し自己申告しない）。
    verdict.model = model
    verdict.finding_id = finding_id
    verdict.blinded = True
    return verdict


def _make_generic_caller(model: str):
    def caller(prompt_path: str, artifact_path: str, finding_id: str, runner) -> Verdict:
        return _generic_model_caller(model, prompt_path, artifact_path, finding_id, runner)
    return caller


def _codex_caller(prompt_path: str, artifact_path: str, finding_id: str, runner) -> Verdict:
    return run_codex_audit(prompt_path, artifact_path, finding_id, runner)


_CALLERS: dict[str, callable] = {
    "codex": _codex_caller,
    "gemini": _make_generic_caller("gemini"),
    "opus": _make_generic_caller("opus"),
    "fable": _make_generic_caller("fable"),
    "local": _make_generic_caller("local"),
}


def run_audit(model: str, prompt_path: str, artifact_path: str, finding_id: str, runner) -> Verdict:
    caller = _CALLERS.get(model)
    if caller is None:
        return _incomplete(model, finding_id, "unknown model (no caller registered)")
    return caller(prompt_path, artifact_path, finding_id, runner)
