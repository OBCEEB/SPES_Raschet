"""Load analysis/configs/main.yaml with path resolution relative to repo root."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "analysis" / "configs" / "main.yaml"


def load_config(path: Path = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("Config root must be a mapping")
    cfg["_config_path"] = str(cfg_path)
    cfg["_repo_root"] = str(REPO_ROOT)
    return cfg


def resolve_path(cfg: Dict[str, Any], key: str) -> Path:
    paths = cfg.get("paths") or {}
    rel = paths.get(key)
    if not rel:
        raise KeyError("paths.{} missing in config".format(key))
    p = Path(rel)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p
