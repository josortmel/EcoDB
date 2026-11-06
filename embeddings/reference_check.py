"""Startup check that the loaded model still means what the stored vectors mean (#910).

With new peft versions Jina v4's LoRA adapters don't load: the model answers, vectors come
out with cosine ~0.2 against the stored ones, and search returns garbage without an error
(from-scratch experiment, 1-nov). Comparing one known vector catches that however peft
stores its keys.
"""
import json
import math
from pathlib import Path

REFERENCE_FILE = Path(__file__).with_name("reference_vector.json")


def cosine(a, b) -> float:
    if len(a) != len(b):
        raise ValueError(f"reference has {len(b)} dims, the model gave {len(a)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def check_reference(model, min_cosine: float, path: Path = REFERENCE_FILE) -> float:
    """Encode the reference text and raise if the vector drifted. Returns the cosine."""
    ref = json.loads(path.read_text(encoding="utf-8"))
    out = model.encode_text(
        texts=[ref["text"]],
        task=ref["task"],
        prompt_name=ref["prompt_name"],
        truncate_dim=ref["truncate_dim"],
    )
    vec = out[0]
    vec = vec.tolist() if hasattr(vec, "tolist") else list(vec)
    score = cosine([float(x) for x in vec], ref["vector"])
    if score < min_cosine:
        raise RuntimeError(
            f"model does not match the stored vectors: cosine {score:.3f} < {min_cosine} "
            "(LoRA adapters not loaded? check the transformers and peft versions)"
        )
    return score
