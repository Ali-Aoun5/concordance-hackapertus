import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pytest
from concordance.fedlex import load_corpus
from concordance.config import load_config

@pytest.fixture(scope="session")
def demo():
    return load_corpus(ROOT / "data" / "demo" / "synthetic_corpus.json")

@pytest.fixture()
def cfg(tmp_path):
    return load_config(llm_mode="replay", cache_dir=tmp_path / "cache", out_dir=tmp_path / "out")
