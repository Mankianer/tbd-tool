"""Datums- und Uhrzeitangaben aus Protokollen in echte Werte umwandeln.

Das Modell liefert zu jedem Termin zwei Dinge:
  - den Datumstext, wie er im Protokoll steht ("13.11.", "25.09", "Sonntag")
  - einen eigenen Vorschlag im Format JJJJ-MM-TT

Python bevorzugt den Text, weil das Ergebnis dann nachvollziehbar ist.
Fehlt das Jahr, wird es aus dem Protokolldatum erschlossen. Nur wenn im Text gar
kein Datum steht (z.B. "nächsten Sonntag"), wird der Vorschlag des Modells genommen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

# Wie weit ein Datum ohne Jahr maximal vor dem Protokolldatum liegen darf,
# bevor wir annehmen, dass das nächste Jahr gemeint ist.
LOOKBACK = timedelta(days=60)

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})(?:\s*\.\s*(\d{4}|\d{2})(?!\d))?")
_TIME_RE = re.compile(r"(?<![\d.])(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*(?:uhr|h)?(?![\d.])", re.I)


@dataclass
class ResolvedDate:
    value: date | None
    warning: str | None = None
    source: str = "text"          # "text" | "model" | "none"


def resolve_date(text: str, model_iso: str, reference: date) -> ResolvedDate:
    """Wandelt eine Datumsangabe in ein ``date`` um.

    ``reference`` ist das Datum des Protokolls (bzw. bei Enddaten das Startdatum).
    """
    for match in _DATE_RE.finditer(text or ""):
        day, month, year_text = int(match.group(1)), int(match.group(2)), match.group(3)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            continue
        warning = None
        if year_text:
            year = int(year_text) + (2000 if len(year_text) == 2 else 0)
            if abs(year - reference.year) <= 1 and _valid(year, month, day):
                return ResolvedDate(date(year, month, day))
            warning = f"Jahr {year_text} in „{text}“ ist unplausibel – stattdessen erschlossen"
        guessed = _infer_year(day, month, reference)
        if guessed:
            return ResolvedDate(guessed, warning)

    parsed = _parse_iso(model_iso)
    if parsed:
        return ResolvedDate(parsed, source="model")
    return ResolvedDate(None, source="none")


def normalize_time(text: str) -> str | None:
    """'17 Uhr' -> '17:00', '9.30' -> '09:30', 'ab ca. 17.00' -> '17:00'."""
    for match in _TIME_RE.finditer(text or ""):
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None


def _infer_year(day: int, month: int, reference: date) -> date | None:
    """Wählt das früheste Jahr, bei dem das Datum nicht zu weit vor ``reference`` liegt."""
    for year in (reference.year - 1, reference.year, reference.year + 1):
        if _valid(year, month, day):
            candidate = date(year, month, day)
            if candidate >= reference - LOOKBACK:
                return candidate
    return None


def _valid(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _parse_iso(text: str) -> date | None:
    try:
        return date.fromisoformat((text or "").strip()[:10])
    except ValueError:
        return None
