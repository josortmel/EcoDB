"""#1160/#1362: the graph is OFF by default in search, in the compose file AND in the code.

Prima measured it on 11-nov with her v5 benchmark (51 queries with a target, on our memories): same quality with
and without the graph, half the time without. Production had EXPAND_GRAPH=0 only in its .env, while the compose
file and search.py defaulted to 1, and the backup does not carry the .env: a recovery from scratch would have
come back with the graph on. If someone turns the default back on, it has to come with a new measurement, and this
test makes that visible in red. Turning it on for one install (EXPAND_GRAPH=1) is still free.
"""

import importlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "api"))


def test_the_compose_file_defaults_the_graph_to_off():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    defaults = re.findall(r"^\s*EXPAND_GRAPH:\s*\$\{EXPAND_GRAPH:-([^}]*)\}", compose, re.M)
    assert defaults == ["0"]


def test_the_code_defaults_the_graph_to_off(monkeypatch):
    monkeypatch.delenv("EXPAND_GRAPH", raising=False)
    import search

    importlib.reload(search)
    assert search.EXPAND_GRAPH is False
    assert search._usa_grafo(None) is False


def test_it_is_a_switch_not_a_removal(monkeypatch):
    monkeypatch.setenv("EXPAND_GRAPH", "1")
    import search

    importlib.reload(search)
    try:
        assert search.EXPAND_GRAPH is True
        assert search._usa_grafo(None) is True
    finally:
        monkeypatch.delenv("EXPAND_GRAPH", raising=False)
        importlib.reload(search)
