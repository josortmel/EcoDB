"""#340: fecha_desde/fecha_hasta are inclusive INSTANTS. A zero-width window or a
midnight fecha_hasta with no results must say so in `warnings` instead of
returning a silent zero. Pure unit tests — no DB.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memories import MemoryListResponse, _date_window_warnings  # noqa: E402

D16 = datetime(2026, 9, 16)
D16_END = datetime(2026, 9, 16, 23, 59, 59, 999999)


def test_zero_width_window_warns():
    w = _date_window_warnings(D16, D16, result_empty=True)
    assert any("zero-width" in x for x in w)


def test_zero_width_window_warns_even_with_results():
    w = _date_window_warnings(D16, D16, result_empty=False)
    assert any("zero-width" in x for x in w)


def test_midnight_hasta_with_empty_result_warns():
    w = _date_window_warnings(datetime(2026, 9, 15), D16, result_empty=True)
    assert any("midnight" in x for x in w)


def test_midnight_hasta_aware_datetime_warns():
    hasta = datetime(2026, 9, 16, tzinfo=timezone.utc)
    w = _date_window_warnings(None, hasta, result_empty=True)
    assert any("midnight" in x for x in w)


def test_no_warning_on_whole_day_window():
    assert _date_window_warnings(D16, D16_END, result_empty=True) == []


def test_no_midnight_warning_when_results_exist():
    assert _date_window_warnings(datetime(2026, 9, 15), D16, result_empty=False) == []


def test_no_warning_without_dates():
    assert _date_window_warnings(None, None, result_empty=True) == []


def test_response_warnings_defaults_to_empty():
    r = MemoryListResponse(items=[], total=0, limit=20, cursor_next=None)
    assert r.warnings == []
