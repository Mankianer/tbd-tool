from datetime import date

from tbd.core.dates import normalize_time, resolve_date

REF = date(2026, 9, 18)


def test_full_date():
    assert resolve_date("02.10.2026", "", REF).value == date(2026, 10, 2)


def test_missing_year_uses_next_occurrence():
    assert resolve_date("13.11.", "", REF).value == date(2026, 11, 13)
    assert resolve_date("15.01.", "", REF).value == date(2027, 1, 15)


def test_recent_past_stays_in_same_year():
    assert resolve_date("28.08.", "", REF).value == date(2026, 8, 28)


def test_implausible_year_is_corrected_with_warning():
    result = resolve_date("13.11.2016", "", REF)
    assert result.value == date(2026, 11, 13)
    assert result.warning


def test_falls_back_to_model_date():
    result = resolve_date("Sonntag", "2026-09-20", REF)
    assert result.value == date(2026, 9, 20) and result.source == "model"


def test_times():
    assert normalize_time("17 Uhr") == "17:00"
    assert normalize_time("ca. 9.30") == "09:30"
    assert normalize_time("17:00-19.00") == "17:00"
    assert normalize_time("") is None
