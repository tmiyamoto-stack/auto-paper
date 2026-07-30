from __future__ import annotations

from .availability import is_available

FAMILY: dict[str, str] = {
    "claude": "claude",
    "fable": "claude",
    "codex": "openai",
    "gemini": "google",
    "opus": "claude",
    "local": "local",
}

# 既知（＝COIを確信的に判定できる）ファミリ集合。ここに無いファミリを持つ id は
# critical 監査に対して INELIGIBLE 扱いにする（未知 id が「唯一の固有ファミリ」として
# COI/quorum をすり抜けるのを禁止する。Fix H）。
_KNOWN_FAMILIES: set[str] = set(FAMILY.values())

# プロバイダ接頭辞（例 "anthropic/claude-opus", "openai/gpt-4o"）→ ファミリ。
# 接頭辞除去後のトークン一致が優先で、それが取れない時のフォールバックに使う。
_PROVIDER_FAMILY: dict[str, str] = {
    "anthropic": "claude",
    "openai": "openai",
    "google": "google",
}

_ROLE_ORDER = ("critical_primary", "critical_secondary", "tiebreak")


def _family(model: str) -> str:
    """モデル id → ファミリ。プロバイダ接頭辞（"anthropic/..."）付き・バージョン付き
    （"claude-opus-4", "codex-1.0"）でも同一プロバイダの派生は同じファミリへ写像する。
    確信的に判定できない id は識別子そのもの（＝未知ファミリ）を返す。"""
    if not isinstance(model, str) or not model:
        return ""
    m = model
    provider = None
    if "/" in m:
        provider, m = m.split("/", 1)
    if m in FAMILY:
        return FAMILY[m]
    for key in FAMILY:
        if m.startswith(key + "-") or m.startswith(key + "."):
            return FAMILY[key]
    if provider is not None and provider.lower() in _PROVIDER_FAMILY:
        return _PROVIDER_FAMILY[provider.lower()]
    return m


def _is_known_family(model: str) -> bool:
    """ファミリを確信的に判定できるか（critical 監査 eligibility の前提）。"""
    return _family(model) in _KNOWN_FAMILIES


def select_auditors(generator_model: str, models_cfg: dict) -> list[str]:
    gen_family = _family(generator_model)
    candidates = [
        models_cfg.get("audit_critical_primary"),
        models_cfg.get("audit_critical_secondary"),
        models_cfg.get("audit_tiebreak"),
    ]
    out: list[str] = []
    for m in candidates:
        if not m:
            continue
        if _family(m) == gen_family:
            continue
        if m not in out:
            out.append(m)
    return out


def select_available_auditors(generator_model: str, role_fallbacks: dict[str, list[str]], prober) -> list[str]:
    """モデル非依存フォールバック選定。役割（critical_primary/critical_secondary/tiebreak）を
    固定順で走査し、各役割のフォールバックリストから「可用 かつ 生成モデルとCOIでない 独立な」
    最初の1件を採用する。全役割で見つからなければ空リスト（呼び出し側でESCALATE_HUMAN）。

    Fix A: ある役割で既選択モデル（重複）や既出ファミリに当たっても break せず、
    リスト内の次の新規適格モデルまで走査を続ける（採用時のみ break）。これにより
    primary=[codex], secondary=[codex, gemini] のような並びで gemini が到達される。
    Fix H: ファミリを確信的に判定できないモデルは critical 監査に INELIGIBLE として除外する。
    選定された監査群は互いに DISTINCT なファミリを持つことを保証する。"""
    gen_family = _family(generator_model)
    out: list[str] = []
    selected_families: set[str] = set()
    for role in _ROLE_ORDER:
        for m in role_fallbacks.get(role, []):
            fam = _family(m)
            if fam not in _KNOWN_FAMILIES:   # 未知ファミリ → INELIGIBLE（Fix H）
                continue
            if fam == gen_family:            # 生成モデルと同一ファミリ = COI
                continue
            if m in out:                     # 既選択モデル（重複）→ 次の新規候補へ（Fix A）
                continue
            if fam in selected_families:     # 既出ファミリ → DISTINCT を強制
                continue
            if not is_available(m, prober):
                continue
            out.append(m)
            selected_families.add(fam)
            break
    return out
