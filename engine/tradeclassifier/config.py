"""Configuration loading + run-stamp (config hash, code version, data snapshot).

Base §25 via ADDENDUM A6: every output file header carries
``{config_sha256, code_version, data_snapshot}``. Determinism pin: seed lives in
config, never in code.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "classifier.yaml"


class ConfigError(ValueError):
    pass


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(path)
    cfg = yaml.safe_load(path.read_text())
    cfg["_config_path"] = str(path)
    cfg["_config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    _validate(cfg)
    return cfg


def _validate(cfg: dict[str, Any]) -> None:
    db = Path(cfg["data"]["db_path"])
    if not db.exists():
        raise ConfigError(f"data.db_path does not exist: {db}")
    cw = cfg.get("composite_weights", {})
    # SPEC_GAPS #2 — a REAL run may not proceed on placeholder weight names.
    if cw.get("require_real_weights") and "real" not in cw:
        cfg["_weights_blocked"] = True
    cuts = cfg["classification"]["cut_points"]
    if not (cuts["strong_buy"] > cuts["add"] > cuts["hold_low"] > cuts["sell"]):
        raise ConfigError(f"cut_points must be strictly monotonic: {cuts}")


def code_version() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "uncommitted"


def data_snapshot(db_path: str | Path) -> str:
    """max(date) of the source tables, joined — the warehouse data version
    (same construction as MarketForge's `_data_version`)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        parts = []
        for label, sql in (
            ("prices", "SELECT MAX(date) FROM daily_prices WHERE ticker='SPY'"),
            ("macro", "SELECT MAX(date) FROM macro_series WHERE series_id='VIXCLS'"),
        ):
            row = con.execute(sql).fetchone()
            parts.append(f"{label}:{row[0]}")
        return "|".join(parts)
    finally:
        con.close()


@dataclass(frozen=True)
class RunStamp:
    config_sha256: str
    code_version: str
    data_snapshot: str

    def as_dict(self) -> dict[str, str]:
        return {
            "config_sha256": self.config_sha256,
            "code_version": self.code_version,
            "data_snapshot": self.data_snapshot,
        }


def run_stamp(cfg: dict[str, Any]) -> RunStamp:
    return RunStamp(
        config_sha256=cfg["_config_sha256"],
        code_version=code_version(),
        data_snapshot=data_snapshot(cfg["data"]["db_path"]),
    )
