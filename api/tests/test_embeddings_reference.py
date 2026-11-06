"""#910: the embedder refuses a model whose vectors don't match the stored ones."""
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reference_check", ROOT / "embeddings" / "reference_check.py")
reference_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reference_check)

REF = json.loads((ROOT / "embeddings" / "reference_vector.json").read_text(encoding="utf-8"))


class FakeModel:
    def __init__(self, vector):
        self.vector = vector
        self.calls = []

    def encode_text(self, texts, task, prompt_name, truncate_dim):
        self.calls.append((texts, task, prompt_name, truncate_dim))
        return [self.vector]


def test_reference_file_is_a_unit_vector_of_its_declared_size():
    assert len(REF["vector"]) == REF["truncate_dim"]
    assert math.sqrt(sum(x * x for x in REF["vector"])) == pytest.approx(1.0, abs=1e-3)


def test_same_vector_passes_and_asks_for_the_reference_text():
    model = FakeModel(REF["vector"])
    assert reference_check.check_reference(model, 0.9) == pytest.approx(1.0)
    assert model.calls == [([REF["text"]], REF["task"], REF["prompt_name"], REF["truncate_dim"])]


def test_broken_lora_shaped_vector_is_refused():
    # the experiment's failure: the model answers with a vector at cosine ~0.2
    noisy = [0.2 * x + (0.98 if i == 0 else 0.0) for i, x in enumerate(REF["vector"])]
    with pytest.raises(RuntimeError, match="does not match the stored vectors"):
        reference_check.check_reference(FakeModel(noisy), 0.9)


def test_wrong_dimension_is_refused():
    with pytest.raises(ValueError, match="dims"):
        reference_check.check_reference(FakeModel([0.1] * 8), 0.9)


def test_requirements_pin_the_versions_that_made_the_stored_vectors():
    lines = (ROOT / "embeddings" / "requirements.txt").read_text(encoding="utf-8").split()
    assert "transformers==4.57.6" in lines
    assert "peft==0.19.1" in lines
