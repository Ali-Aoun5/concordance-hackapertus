"""Rule output feeds the verifier prompt, and the prompt is the cache key.
It must therefore not depend on Python's per-process hash seed."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = """
import json, hashlib, sys
sys.path.insert(0, %r)
from concordance.fedlex import load_corpus
from concordance.rules import rule_divergences
meta, arts = load_corpus(%r)
extra = [{"de": "Der Arbeitgeber und der Arbeitnehmer melden dies im Kanton und im Bund.",
          "fr": "L'employeur et le travailleur annoncent cela au canton et a la commune.",
          "it": "Il datore di lavoro e il lavoratore comunicano questo al cantone e al comune."}]
out = [d.to_dict() for a in arts for d in rule_divergences(a.texts)] + [d.to_dict() for t in extra for d in rule_divergences(t)]
print(hashlib.sha1(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
"""

def test_rule_output_is_identical_under_different_hash_seeds():
    corpus = ROOT / "data" / "demo" / "synthetic_corpus.json"
    digests = set()
    for seed in ("1", "2", "3", "4"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", CODE % (str(ROOT / "src"), str(corpus))],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        digests.add(r.stdout.strip())
    assert len(digests) == 1
