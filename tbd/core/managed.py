"""Properties schreiben, ohne Handeingaben zu überschreiben.

Die Regel: **Was ein Mensch geändert hat, überschreibt das Tool nie.**

Für jede Property vergleicht ``ManagedWriter.write`` drei Werte:
  - ``current``: was gerade in der Notiz steht
  - ``last``:    was das Tool zuletzt geschrieben hat (aus dem State)
  - ``new``:     was das Tool jetzt schreiben möchte

Fälle:
  current == new                      -> nichts zu tun
  current == last (oder Feld leer)    -> Wert gehört dem Tool, wird aktualisiert
  new == last                         -> Mensch hat geändert, Protokoll sagt nichts Neues
                                         -> Handeingabe bleibt, kein Konflikt
  sonst                               -> Mensch hat geändert UND Protokoll sagt etwas Neues
                                         -> Konflikt im Prüfbericht
                                         (außer: Konflikt wurde angenommen oder ignoriert)
Liefert das Protokoll keinen Wert (new leer), bleibt der vorhandene Wert stehen.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .notes import Note
from .review import Option, Review, ReviewItem
from .state import IgnoreList, State

_MISSING = object()


@dataclass
class RunDecisions:
    """Entscheidungen aus dem Prüfbericht, die im aktuellen Lauf umgesetzt werden."""
    accepted_conflicts: set[str] = field(default_factory=set)
    deletions: set[str] = field(default_factory=set)
    done: list[str] = field(default_factory=list)


def normalize_value(value):
    """Macht Werte vergleichbar: Datum -> 'JJJJ-MM-TT', leer -> None, Listen -> Liste von Strings."""
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        items = [normalize_value(v) for v in value]
        items = [str(v) for v in items if v is not None]
        return items or None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip() or None


def conflict_id(note_id: str, key: str, new_value) -> str:
    digest = hashlib.sha1(repr(new_value).encode()).hexdigest()[:8]
    return f"conflict:{note_id}:{key}:{digest}"


class ManagedWriter:
    def __init__(self, root: Path, state: State, review: Review, ignored: IgnoreList,
                 decisions: RunDecisions):
        self.root = root
        self.state = state
        self.review = review
        self.ignored = ignored
        self.decisions = decisions

    def write(self, note: Note, note_id: str, desired: dict) -> None:
        """Setzt die gewünschten Properties in ``note.props`` (speichert die Notiz nicht)."""
        entry = self.state.entry(note_id)
        fields = entry["fields"]
        note.props.setdefault("id", note_id)

        for key, new_raw in desired.items():
            new = normalize_value(new_raw)
            current = normalize_value(note.props.get(key))
            last = fields.get(key, _MISSING)

            if new is None:
                # Protokoll liefert nichts -> nichts überschreiben; Feld aber sichtbar machen
                note.props.setdefault(key, None)
                continue
            if current == new:
                fields[key] = new
                continue

            owned_by_tool = (current is None and last in (_MISSING, None)) or current == last
            if owned_by_tool:
                note.props[key] = new_raw
                fields[key] = new
                continue
            if new == last:
                continue      # Handeingabe, Protokoll unverändert -> nichts zu melden

            cid = conflict_id(note_id, key, new)
            if cid in self.decisions.accepted_conflicts:
                note.props[key] = new_raw
                fields[key] = new
                self.decisions.done.append(f"Konflikt übernommen: {note.link} – {key} = {_show(new)}")
            elif cid not in self.ignored:
                self.review.add(ReviewItem(
                    id=cid,
                    title=f"{note.link} – {key}",
                    details=[
                        f"Von Hand eingetragen: {_show(current)}",
                        f"Laut Protokoll jetzt: {_show(new)}",
                    ],
                    options=[
                        Option("accept", "Protokollwert übernehmen"),
                        Option("ignore", "Handeingabe behalten"),
                    ],
                ))
        entry["path"] = note.path.relative_to(self.root).as_posix()

    def is_untouched(self, note: Note, note_id: str) -> bool:
        """True, wenn alle vom Tool geschriebenen Werte noch unverändert in der Notiz stehen."""
        entry = self.state.get(note_id) or {}
        return all(normalize_value(note.props.get(k)) == v for k, v in entry.get("fields", {}).items())


def _show(value) -> str:
    if value is None:
        return "_(leer)_"
    if isinstance(value, list):
        return ", ".join(value)
    return f"`{value}`" if "[[" not in value else value
