from __future__ import annotations

"""モデル可用性プロービング（本番は codex CLI on PATH / gemini key / opus / local 到達性を確認するが、
ここでは呼び出し元が注入する prober(model) -> bool に完全委譲する）。"""


def is_available(model: str, prober) -> bool:
    return bool(prober(model))


def available_models(candidates: list[str], prober) -> list[str]:
    out: list[str] = []
    for m in candidates:
        if m in out:
            continue
        if is_available(m, prober):
            out.append(m)
    return out
