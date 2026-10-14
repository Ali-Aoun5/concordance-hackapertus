"""Configuration from environment / .env. No third-party dependency."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # .../track_2b


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Config:
    base_url: str
    api_key: str
    small_model: str
    large_model: str
    llm_mode: str            # replay | live
    workers: int
    cache_dir: Path
    out_dir: Path
    data_dir: Path
    seed: int = 7
    large_base_url: str = ""   # optional: serve the 70B model from a different URL


def load_config(llm_mode: str | None = None, **over) -> Config:
    _load_dotenv(ROOT / ".env")
    key = os.environ.get("CSCS_API_KEY", "").strip()
    mode = (llm_mode or os.environ.get("CONCORDANCE_LLM_MODE", "auto")).lower()
    base_url = os.environ.get("CSCS_BASE_URL", "https://api.inference.cscs.ch/v1").rstrip("/")
    if mode == "auto":
        # A key means CSCS; a non-CSCS URL means an on-prem server (e.g. vLLM) that needs no key.
        mode = "live" if (key or "cscs.ch" not in base_url) else "replay"
    cfg = Config(
        base_url=base_url,
        api_key=key,
        # Placeholders: run `python -m concordance models` and put the exact ids in .env
        small_model=os.environ.get("APERTUS_SMALL_MODEL", "swiss-ai/Apertus-v1.5-8B"),
        large_model=os.environ.get("APERTUS_LARGE_MODEL", "swiss-ai/Apertus-v1.5-70B"),
        llm_mode=mode,
        large_base_url=os.environ.get("APERTUS_LARGE_BASE_URL", "").strip(),
        workers=int(os.environ.get("CONCORDANCE_WORKERS", "4")),
        cache_dir=Path(os.environ.get("CONCORDANCE_CACHE_DIR", ROOT / "data" / "cache")),
        out_dir=Path(os.environ.get("CONCORDANCE_OUT_DIR", ROOT / "out")),
        data_dir=ROOT / "data",
    )
    for k, v in over.items():
        if v is not None:
            setattr(cfg, k, v)
    return cfg
