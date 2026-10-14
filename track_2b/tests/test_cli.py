from concordance.cli import _hoist_llm_mode, build_parser
from concordance.config import load_config

def test_llm_mode_accepted_after_the_command():
    argv = _hoist_llm_mode(["demo", "--llm-mode", "replay", "--max-articles", "60"])
    assert argv[:2] == ["--llm-mode", "replay"]
    args = build_parser().parse_args(argv)
    assert args.cmd == "demo" and args.llm_mode == "replay" and args.max_articles == 60

def test_llm_mode_accepted_before_and_with_equals():
    assert _hoist_llm_mode(["--llm-mode", "live", "demo"]) == ["--llm-mode", "live", "demo"]
    assert _hoist_llm_mode(["demo", "--llm-mode=replay"])[0] == "--llm-mode=replay"

def test_default_models_are_the_recorded_v15_ids(monkeypatch):
    for k in ("APERTUS_SMALL_MODEL", "APERTUS_LARGE_MODEL", "CSCS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("concordance.config._load_dotenv", lambda p: None)
    cfg = load_config(llm_mode="replay")
    assert (cfg.small_model, cfg.large_model) == ("swiss-ai/Apertus-v1.5-8B", "swiss-ai/Apertus-v1.5-70B")
