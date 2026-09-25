"""C21 (#365 system part): if the query names exactly one of the actor's agents
and no agent_identifier filter was passed, but results include other agents'
memories, say so in `warnings`. Labels only — ranking untouched. Pure test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search import agent_name_warning  # noqa: E402

IDS = ["Eco", "Prima", "Hilo", "SIN_AUTOR"]


def mem(agent):
    return {"agent_identifier": agent, "source_type": "memory"}


def test_warns_when_named_agent_results_are_mixed():
    w = agent_name_warning("fotos de Eco", None, IDS, [mem("Eco"), mem("Prima"), mem("Prima")])
    assert w == ("query names agent 'Eco' but results include other agents' memories (2 of 3); "
                 "pass agent_identifier=\"Eco\" to restrict")


def test_case_insensitive_whole_word():
    assert agent_name_warning("FOTOS DE ECO", None, IDS, [mem("Prima")])
    assert agent_name_warning("ecodb graph_context", None, IDS, [mem("Prima")]) is None


def test_silent_when_filtered_by_agent():
    assert agent_name_warning("fotos de Eco", "Eco", IDS, [mem("Prima")]) is None


def test_silent_when_no_agent_named():
    assert agent_name_warning("mapa de Las Tierras Rotas", None, IDS, [mem("Prima")]) is None


def test_silent_when_two_agents_named():
    assert agent_name_warning("Eco y Prima hablando", None, IDS, [mem("Hilo")]) is None


def test_silent_when_all_results_are_the_named_agent():
    assert agent_name_warning("fotos de Eco", None, IDS, [mem("Eco"), mem("Eco")]) is None


def test_sin_autor_is_ignored():
    assert agent_name_warning("memorias SIN_AUTOR", None, IDS, [mem("Prima")]) is None


def test_document_chunks_do_not_count():
    res = [mem("Eco"), {"agent_identifier": None, "source_type": "document_chunk"}]
    assert agent_name_warning("fotos de Eco", None, IDS, res) is None
