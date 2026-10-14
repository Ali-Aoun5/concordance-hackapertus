from concordance.corrupt import INJECTORS, build_eval_set
from concordance.rules import rule_divergences
import random

def test_every_injection_changes_text_and_is_logged(demo):
    meta, arts = demo
    cases = build_eval_set(arts, seed=1, max_per_type=5, exclude_art_ids=set(meta["planted"]))
    assert any(c.gold for c in cases) and any(c.gold is None for c in cases)
    for c in cases:
        if not c.gold:
            continue
        orig = next(a for a in arts if a.art_id == c.art_id)
        assert c.texts[c.gold["lang"]] != orig.texts[c.gold["lang"]]
        for l in ("de", "fr", "it"):
            if l != c.gold["lang"]:
                assert c.texts[l] == orig.texts[l]

def test_deterministic(demo):
    meta, arts = demo
    a = build_eval_set(arts, seed=3, max_per_type=4)
    b = build_eval_set(arts, seed=3, max_per_type=4)
    assert [c.to_dict() for c in a] == [c.to_dict() for c in b]

def test_injected_cases_are_detected_by_rules_with_right_type(demo):
    meta, arts = demo
    cases = build_eval_set(arts, seed=2, max_per_type=5, exclude_art_ids=set(meta["planted"]))
    for c in cases:
        if c.gold:
            types = {d.type for d in rule_divergences(c.texts)}
            assert c.gold["type"] in types, (c.case_id, c.gold, types)

def test_modality_injection_never_keeps_same_force():
    rng = random.Random(0)
    out = INJECTORS["modality"]("Elle ne peut pas dépasser la limite.", "fr", rng)
    assert out is None or "doit pas" not in out[0]
