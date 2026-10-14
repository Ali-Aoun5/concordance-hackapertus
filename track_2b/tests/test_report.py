import json
import pytest
from concordance import report

TPL = """<html><script>if (raw.trim() === "__DATA__") { useSample(); }</script>
<script id="data" type="application/json">__DATA__</script></html>"""

def test_placeholder_only_replaced_inside_data_tag():
    out = report._inject(TPL, json.dumps({"a": "</script>".replace("</", "<\\/")}))
    assert out.count('=== "__DATA__"') == 1          # the page's own check is untouched
    assert '{"a"' in out and '<script id="data" type="application/json">{"a"' in out

def test_missing_placeholder_fails_loudly():
    with pytest.raises(ValueError):
        report._inject("<html></html>", "{}")
