from __future__ import annotations

import json
from dataclasses import dataclass, field

_DEFAULT_THRESHOLDS = {"g15_effect_pct": 0.20, "g15_n_pct": 0.05}


@dataclass
class Config:
    dict_paths: dict[str, str]
    raw_data_dir: str
    output_root: str
    models: dict[str, str]
    gate_thresholds: dict[str, float]
    # プロファイル配線（DESIGN_generic_clinical §6）。旧 config には無いため default {}。
    profiles: dict[str, dict] = field(default_factory=dict)
    # モデル非依存フォールバック（監査オーケストレーション）。旧 config には無いため default []/{}。
    model_pool: list = field(default_factory=list)
    audit_role_fallbacks: dict = field(default_factory=dict)


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    thresholds = dict(_DEFAULT_THRESHOLDS)
    thresholds.update(data.get("gate_thresholds", {}))
    return Config(
        dict_paths=data.get("dict_paths", {}),
        raw_data_dir=data.get("raw_data_dir", ""),
        output_root=data.get("output_root", ""),
        models=data.get("models", {}),
        gate_thresholds=thresholds,
        profiles=data.get("profiles", {}),
        model_pool=data.get("model_pool", []),
        audit_role_fallbacks=data.get("audit_role_fallbacks", {}),
    )
