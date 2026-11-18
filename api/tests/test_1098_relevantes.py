"""#1098: el umbral por mitad de decisiones vigentes (SUELO y MARGEN) y la regla de las filas que solo llegan
por texto. Sin base ni red: _relevantes es una función pura sobre las candidatas ya puntuadas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import decisiones  # noqa: E402
from decisiones import MARGEN, SUELO, _relevantes  # noqa: E402


def _c(i, cos, r_vec=1, r_txt=None, content=""):
    return {"id": i, "cos": cos, "r_vec": r_vec, "r_txt": r_txt, "content": content}


def test_nada_relevante_deja_la_mitad_vacia():
    # «receta de lentejas»: el máximo del set de desarrollo fue 0,52; no se rellena con ruido.
    assert _relevantes([_c("a", 0.52), _c("b", 0.49)], "receta de lentejas") == []


def test_por_debajo_del_suelo_no_entra_aunque_sea_la_mejor():
    assert _relevantes([_c("a", SUELO - 0.001)], "tema") == []


def test_el_margen_corta_las_lejanas_de_la_mejor():
    filas = [_c("a", 0.71), _c("b", 0.71 - MARGEN + 0.001), _c("c", 0.71 - MARGEN - 0.001)]
    assert [f["id"] for f in _relevantes(filas, "tema")] == ["a", "b"]


def test_solo_por_texto_necesita_la_mitad_de_las_palabras():
    tema = "push y merge sin pedir permiso"   # con contenido: push, merge, sin, pedir, permiso (5)
    buena = _c("t1", 0.65, r_vec=None, r_txt=1, content="Pepe: push y merge sin pedir permiso nunca")
    pobre = _c("t2", 0.65, r_vec=None, r_txt=2, content="el permiso de los hobbies")
    assert [f["id"] for f in _relevantes([buena, pobre], tema)] == ["t1"]


def test_por_vector_no_mira_las_palabras():
    assert [f["id"] for f in _relevantes([_c("v", 0.65, content="nada en común")], "push y merge")] == ["v"]


def test_sin_embedding_cuenta_como_cero():
    assert _relevantes([_c("x", None)], "tema") == []


def test_las_palabras_vacias_no_cuentan():
    assert decisiones._palabras("la de el en y a que lo al es push") == {"push"}
