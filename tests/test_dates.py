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


# --- Jahr aus dem Zusammenhang (Fall Protokoll 2025-05-23: "Termine Pferdefreizeit (2026)") ---

def test_model_year_from_context_wins_over_rule():
    result = resolve_date("08.05", "2026-05-08", date(2025, 5, 23))
    assert result.value == date(2026, 5, 8)
    assert result.source == "model-year"
    assert "2026" in result.warning          # Abweichung von der Regel wird gemeldet


def test_model_year_matching_rule_gives_no_warning():
    result = resolve_date("13.11.", "2026-11-13", REF)
    assert result.value == date(2026, 11, 13) and result.warning is None


def test_model_with_other_day_is_not_trusted():
    assert resolve_date("13.11.", "2026-11-14", REF).value == date(2026, 11, 13)


def test_implausible_model_year_is_not_trusted():
    assert resolve_date("13.11.", "2031-11-13", REF).value == date(2026, 11, 13)


def test_explicit_year_in_text_beats_model():
    assert resolve_date("13.11.2026", "2027-11-13", REF).value == date(2026, 11, 13)


def test_end_date_from_context():
    start = resolve_date("08.05", "2026-05-08", date(2025, 5, 23)).value
    assert resolve_date("10.05", "2026-05-10", start).value == date(2026, 5, 10)
