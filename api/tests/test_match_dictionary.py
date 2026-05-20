"""Tests for _match_dictionary pure helper (no GLiNER, no DB).

Covers:
- Longest-match wins over shorter prefixes.
- Word-boundary regex \\b prevents substring false positives.
- Spans replaced with same-length spaces to preserve token offsets.
- Provenance source="dictionary" on dict-matched entities.

Helper `_match_dictionary` es funcion pura que opera sobre `_dictionary_cache`
(lista de tuplas precompiladas). Estos tests manipulan _dictionary_cache
directamente para evitar dependencia de BD + cargar el cache real.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import gliner_service
from gliner_service import _match_dictionary


def _build_cache(entries: list[tuple[str, str]]) -> list[tuple[re.Pattern, str, str]]:
    """Construye el cache pre-compilado equivalente al de load_dictionary_to_cache.

    entries: lista de (name_normalized, entity_type). Original name = capitalized
    primera letra para tests legibles.
    """
    # Ordenar por longitud DESC — longest-match wins.
    sorted_entries = sorted(entries, key=lambda e: len(e[0]), reverse=True)
    return [
        (re.compile(r"\b" + re.escape(name_norm) + r"\b"), etype, name_norm.title())
        for name_norm, etype in sorted_entries
    ]


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cache antes y después de cada test para aislamiento."""
    original = gliner_service._dictionary_cache.copy()
    yield
    gliner_service._dictionary_cache = original


def test_match_basic_single_entity():
    """Texto con una entidad conocida → 1 match con source=dictionary."""
    gliner_service._dictionary_cache = _build_cache([("alan", "persona")])
    entities, residual = _match_dictionary("hablé con alan ayer")
    assert len(entities) == 1
    assert entities[0]["text"] == "alan"
    assert entities[0]["label"] == "persona"
    assert entities[0]["source"] == "dictionary"
    assert entities[0]["score"] == 1.0
    # Residual con espacios donde estaba "alan" (4 chars).
    assert residual == "hablé con      ayer"


def test_match_longest_wins_overlapping_entries():
    """Longest match wins: 'eco consulting' matches before standalone 'eco'."""
    gliner_service._dictionary_cache = _build_cache([
        ("eco", "agente_ia"),
        ("eco consulting", "organizacion"),
    ])
    entities, residual = _match_dictionary("trabajo en eco consulting")
    # Solo debe haber 1 match — el largo. "eco" no debe aparecer adicional.
    assert len(entities) == 1
    assert entities[0]["text"] == "eco consulting"
    assert entities[0]["label"] == "organizacion"


def test_word_boundary_no_substring_match():
    """'eco' in dict does NOT match 'ecosistema' — word boundary enforced."""
    gliner_service._dictionary_cache = _build_cache([("eco", "agente_ia")])
    entities, residual = _match_dictionary("hablamos de ecosistema y ecologia")
    # "ecosistema" y "ecologia" NO deben matchear.
    assert len(entities) == 0
    assert residual == "hablamos de ecosistema y ecologia"


def test_word_boundary_inside_word_no_match():
    """'ala' en dict NO matchea 'alan' (subset de palabra mas larga)."""
    gliner_service._dictionary_cache = _build_cache([("ala", "persona")])
    entities, _ = _match_dictionary("hola alan")
    assert len(entities) == 0


def test_residual_preserves_offsets_with_spaces():
    """Matched spans are replaced with same-length spaces, not removed.

    Without replacement, removing a matched span could concatenate surrounding
    characters into a new token that GLiNER misidentifies as a different entity.
    """
    gliner_service._dictionary_cache = _build_cache([("alan", "persona")])
    entities, residual = _match_dictionary("PrAlanima trabajo")
    # "the platform owner" debe matchear como palabra completa? No, esta dentro de una palabra
    # — word boundary impide match. Verifico que NO matchea.
    # Actualizamos el test: word-boundary también afecta este caso.
    assert len(entities) == 0
    # Pero si el texto fuera "alan trabajo" (con espacios alrededor):
    entities, residual = _match_dictionary("alan trabajo")
    assert len(entities) == 1
    # Verifico que "alan" se reemplaza con 4 espacios.
    assert residual == "     trabajo"  # 4 espacios + " trabajo"


def test_multiple_entities_in_one_text():
    """Múltiples entidades, todas matcheadas por el dict."""
    gliner_service._dictionary_cache = _build_cache([
        ("alan", "persona"),
        ("sevilla", "lugar"),
    ])
    entities, residual = _match_dictionary("alan vive en sevilla")
    assert len(entities) == 2
    labels = {e["label"] for e in entities}
    assert labels == {"persona", "lugar"}


def test_empty_text_returns_empty():
    """Texto vacío → no entidades, residual vacío."""
    gliner_service._dictionary_cache = _build_cache([("alan", "persona")])
    entities, residual = _match_dictionary("")
    assert entities == []
    assert residual == ""


def test_empty_dictionary_returns_text_unchanged():
    """Diccionario vacío → no matches, residual igual al texto original."""
    gliner_service._dictionary_cache = []
    text = "alan trabajó en sevilla"
    entities, residual = _match_dictionary(text)
    assert entities == []
    assert residual == text


def test_provenance_source_dictionary():
    """Todas las entidades del helper tienen source='dictionary' (provenance)."""
    gliner_service._dictionary_cache = _build_cache([
        ("alan", "persona"),
        ("eco consulting", "organizacion"),
    ])
    entities, _ = _match_dictionary("alan trabajó en eco consulting")
    assert all(e["source"] == "dictionary" for e in entities)
    assert all(e["score"] == 1.0 for e in entities)


def test_case_insensitive_match():
    """'ALAN' matchea contra dict 'alan' (lookup sobre text.lower())."""
    gliner_service._dictionary_cache = _build_cache([("alan", "persona")])
    entities, _ = _match_dictionary("hola ALAN buen día")
    assert len(entities) == 1
    # Texto original preservado en `text` field.
    assert entities[0]["text"] == "ALAN"
    assert entities[0]["label"] == "persona"


def test_dedupe_same_entity_multiple_occurrences():
    """'alan' aparece 3 veces → 3 matches separados (uno por ocurrencia).

    NOTA: el dedupe por nombre lo hace link_entities_from_content (caller),
    no _match_dictionary. Aquí cada ocurrencia es un span distinct.
    """
    gliner_service._dictionary_cache = _build_cache([("alan", "persona")])
    entities, residual = _match_dictionary("alan llamó a alan sobre alan")
    assert len(entities) == 3
    assert all(e["text"] == "alan" for e in entities)
