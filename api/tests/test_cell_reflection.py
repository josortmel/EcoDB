"""#393 (2): el cluster semanal «Arcos y puntos ciegos» tomaba como miembros las 2 memorias de más peso de TODA
la vida del agente (ORDER BY weight DESC LIMIT 2 sin ventana), así que cada semana colgaban de él las mismas
memorias de abril. Los miembros tienen que ser memorias de la propia semana."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402


def _m(i, w):
    return {"id": f"m{i}", "weight": w, "created_at": datetime(2026, 10, 5 + i, tzinfo=timezone.utc)}


def test_members_are_the_weeks_heaviest():
    week = [_m(0, 0.5), _m(1, 0.9), _m(2, 0.7), _m(3, 0.6)]
    assert cw._reflection_member_ids(week) == ["m1", "m2"]


def test_only_from_the_given_week_list():
    week = [_m(0, 0.5), _m(1, 0.5)]
    assert sorted(cw._reflection_member_ids(week)) == ["m0", "m1"]
