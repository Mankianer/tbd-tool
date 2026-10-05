"""Gedächtnis des Tools – liegt im Vault unter .tbd/ und wandert mit.

``State`` (.tbd/state.json)
    Merkt sich pro Notiz (über ihre id), welche Property-Werte das Tool zuletzt
    selbst geschrieben hat. Nur so lässt sich erkennen, ob ein Mensch einen Wert
    geändert hat. Außerdem: Pfad der Notiz und ob sie vom Nutzer gelöscht wurde.

``IgnoreList`` (.tbd/ignored.yaml)
    Ids von Prüfbericht-Einträgen, die auf "ignorieren" gesetzt wurden.
    Kann bei Bedarf von Hand bearbeitet werden.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml


class State:
    FILE_NAME = "state.json"

    def __init__(self, path: Path, data: dict | None = None):
        self.path = path
        self.data = data or {"version": 1, "notes": {}}

    @classmethod
    def load(cls, tool_dir: Path) -> "State":
        path = tool_dir / cls.FILE_NAME
        if path.exists():
            return cls(path, json.loads(path.read_text(encoding="utf-8")))
        return cls(path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True)
        self.path.write_text(text + "\n", encoding="utf-8")

    @property
    def notes(self) -> dict[str, dict]:
        return self.data.setdefault("notes", {})

    def entry(self, note_id: str) -> dict:
        """Eintrag einer Notiz (wird bei Bedarf angelegt).

        Aufbau: {"path": "Termine/….md", "fields": {property: wert}, "deleted": bool}
        """
        entry = self.notes.setdefault(note_id, {})
        entry.setdefault("fields", {})
        return entry

    def get(self, note_id: str) -> dict | None:
        return self.notes.get(note_id)

    def remove(self, note_id: str) -> None:
        self.notes.pop(note_id, None)

    def ids_with_prefix(self, prefix: str) -> list[str]:
        return [i for i in self.notes if i.startswith(prefix)]


class IgnoreList:
    FILE_NAME = "ignored.yaml"
    HEADER = (
        "# Prüfbericht-Einträge, die auf \"ignorieren\" gesetzt wurden.\n"
        "# Eine Zeile löschen = der Eintrag taucht beim nächsten Lauf wieder auf.\n"
    )

    def __init__(self, path: Path, ids: set[str] | None = None):
        self.path = path
        self.ids = ids or set()

    @classmethod
    def load(cls, tool_dir: Path) -> "IgnoreList":
        path = tool_dir / cls.FILE_NAME
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            return cls(path, {str(i) for i in data})
        return cls(path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = yaml.safe_dump(sorted(self.ids), allow_unicode=True) if self.ids else "[]\n"
        self.path.write_text(self.HEADER + body, encoding="utf-8")

    def add(self, item_id: str) -> None:
        self.ids.add(item_id)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self.ids
