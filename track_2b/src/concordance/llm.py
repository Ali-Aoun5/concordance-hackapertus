"""OpenAI-compatible chat client for the CSCS Apertus endpoint, with a disk cache.

Two modes:
  live    -> use the cache when it has the answer, otherwise call the API and record it.
  replay  -> cache only. Zero network access. A miss raises CacheMiss.

Replay is what judges run: every model response used in the report ships in
data/cache/*.jsonl, so `make run` reproduces the numbers without an API key and
inside a container with networking disabled (air-gapped).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path


class CacheMiss(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


class _Fatal(LLMError):
    """Errors that retrying cannot fix (bad key, no permission, unknown model)."""


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    model: str
    key: str


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def make_key(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    blob = json.dumps({"m": model, "msgs": messages, "t": temperature, "mx": max_tokens},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMClient:
    def __init__(self, base_url: str, api_key: str, mode: str, cache_dir: Path,
                 timeout: int = 180, max_retries: int = 5, model_urls: dict | None = None):
        assert mode in ("live", "replay")
        self.base_url = base_url.rstrip("/")
        self.model_urls = {m: u.rstrip("/") for m, u in (model_urls or {}).items()}
        self.api_key = api_key
        self.mode = mode
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._cache: dict = {}
        self._loaded: set = set()
        self._session = None
        self.counters: dict = {}          # model -> dict

    # ---------------------------------------------------------------- cache
    def _cache_path(self, model: str) -> Path:
        return self.cache_dir / f"{_slug(model)}.jsonl"

    def _load(self, model: str) -> None:
        if model in self._loaded:
            return
        with self._lock:
            if model in self._loaded:
                return
            p = self._cache_path(model)
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        self._cache[rec["key"]] = rec
                    except (json.JSONDecodeError, KeyError):
                        continue
            self._loaded.add(model)

    def _append(self, model: str, rec: dict) -> None:
        with self._lock:
            self._cache[rec["key"]] = rec
            with self._cache_path(model).open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------------------------------------------------------------- counters
    def _count(self, model: str, ptok: int, ctok: int, cached: bool) -> None:
        with self._lock:
            c = self.counters.setdefault(model, {"calls": 0, "live_calls": 0, "cache_hits": 0,
                                                  "prompt_tokens": 0, "completion_tokens": 0})
            c["calls"] += 1
            c["cache_hits" if cached else "live_calls"] += 1
            c["prompt_tokens"] += ptok
            c["completion_tokens"] += ctok

    def snapshot(self) -> dict:
        with self._lock:
            return {m: dict(c) for m, c in self.counters.items()}

    # ---------------------------------------------------------------- API
    def _http(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def list_models(self) -> list:
        if not self.api_key and "cscs.ch" in self.base_url:
            raise LLMError("CSCS_API_KEY is not set (put it in .env).")
        r = self._http().get(f"{self.base_url}/models", timeout=self.timeout,
                             headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
        r.raise_for_status()
        return [m.get("id", "?") for m in r.json().get("data", [])]

    def chat(self, model: str, messages: list, temperature: float = 0.0,
             max_tokens: int = 1400) -> LLMResult:
        self._load(model)
        key = make_key(model, messages, temperature, max_tokens)
        rec = self._cache.get(key)
        if rec is not None:
            self._count(model, rec["prompt_tokens"], rec["completion_tokens"], True)
            return LLMResult(rec["response"], rec["prompt_tokens"], rec["completion_tokens"],
                             True, model, key)
        if self.mode == "replay":
            raise CacheMiss(f"no cached response for {model} (key {key[:10]}…); "
                            "run with CSCS_API_KEY to record it")
        if not self.api_key and "cscs.ch" in self.base_url:
            raise LLMError("live mode against CSCS needs CSCS_API_KEY")

        base = self.model_urls.get(model, self.base_url)
        payload = {"model": model, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens, "seed": 0}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last = ""
        for attempt in range(self.max_retries):
            try:
                r = self._http().post(f"{base}/chat/completions", json=payload,
                                      headers=headers, timeout=self.timeout)
                if r.status_code in (401, 403, 404):
                    raise _Fatal(f"HTTP {r.status_code} (not retried): {r.text[:200]}. "
                                 "Check CSCS_API_KEY and that the model id is enabled for your key.")
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {r.status_code}: {r.text[:200]}"
                    time.sleep(min(2 ** attempt * 2, 40))
                    continue
                if r.status_code == 400 and "seed" in payload and "seed" in r.text.lower():
                    payload.pop("seed")            # some servers reject 'seed'
                    continue
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"] or ""
                usage = data.get("usage") or {}
                ptok = int(usage.get("prompt_tokens") or sum(len(m["content"]) for m in messages) // 3.5)
                ctok = int(usage.get("completion_tokens") or len(text) // 3.5)
                rec = {"key": key, "model": model, "response": text, "prompt_tokens": ptok,
                       "completion_tokens": ctok, "ts": int(time.time())}
                self._append(model, rec)
                self._count(model, ptok, ctok, False)
                return LLMResult(text, ptok, ctok, False, model, key)
            except _Fatal:
                raise
            except Exception as e:   # network errors, JSON errors
                last = f"{type(e).__name__}: {e}"
                time.sleep(min(2 ** attempt * 2, 40))
        raise LLMError(f"giving up after {self.max_retries} attempts: {last}")


# ---------------------------------------------------------------- JSON parsing
def parse_json(text: str):
    """Extract the first JSON object from a model reply. Returns None on failure."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    chunk = t[start:end + 1]
    for candidate in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None
