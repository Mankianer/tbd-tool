"""Zugriff auf den Obsidian-Vault: Ordner, Notizen finden und aus Vorlagen anlegen."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import Config
from .names import NameIndex, normalize_name, safe_filename, strip_link
from .notes import Note

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# Übersichtsseiten, die bei "tbd init" angelegt werden: Dateiname -> Vorlage
OVERVIEWS = {
    "Anstehende Termine.md": "overview_upcoming.md",
    "Deadlines.md": "overview_deadlines.md",
    "Besprechungen.md": "overview_meetings.md",
}


class Vault:
    def __init__(self, config: Config):
        self.config = config
        self.root = config.vault

    # --- Ordner -------------------------------------------------------------

    def folder(self, key: str) -> Path:
        """Pfad eines Ordners laut Konfiguration, z.B. folder('persons')."""
        return self.root / self.config.folders[key]

    @property
    def tool_dir(self) -> Path:
        return self.config.tool_dir

    @property
    def review_path(self) -> Path:
        return self.folder("system") / "Prüfbericht.md"

    @property
    def attachments_dir(self) -> Path:
        return self.folder("protocols") / self.config.folders["attachments"]

    def ensure_structure(self) -> None:
        """Legt alle Ordner und die Übersichtsseiten an (vorhandene bleiben unverändert)."""
        for key in ("protocols", "appointments", "topics", "persons", "overviews", "system"):
            self.folder(key).mkdir(parents=True, exist_ok=True)
        self.tool_dir.mkdir(parents=True, exist_ok=True)
        for filename, template in OVERVIEWS.items():
            path = self.folder("overviews") / filename
            if not path.exists():
                path.write_text(self.render_template(template), encoding="utf-8")
                log.info("Übersicht angelegt: %s", path.relative_to(self.root))

    # --- Notizen lesen ------------------------------------------------------

    def notes(self, key: str) -> list[Note]:
        folder = self.folder(key)
        if not folder.exists():
            return []
        return [Note.load(p) for p in sorted(folder.glob("*.md"))]

    def notes_by_id(self, key: str) -> dict[str, Note]:
        """Alle Notizen eines Ordners mit 'id'-Property, nach id."""
        return {str(n.props["id"]): n for n in self.notes(key) if n.props.get("id")}

    def name_index(self, key: str) -> NameIndex:
        return NameIndex(self.notes(key))

    # --- Notizen anlegen ----------------------------------------------------

    def render_template(self, template: str) -> str:
        text = (TEMPLATE_DIR / template).read_text(encoding="utf-8")
        for key, folder in self.config.folders.items():
            text = text.replace("{{" + key + "}}", folder)
        return text

    def new_note(self, path: Path, template: str) -> Note:
        """Erzeugt eine neue (noch nicht gespeicherte) Notiz aus einer Vorlage."""
        return Note.parse(path, self.render_template(template))

    def load_or_new(self, path: Path, template: str) -> Note:
        """Lädt die Notiz oder erzeugt sie aus der Vorlage, falls es sie noch nicht gibt."""
        return Note.load(path) if path.exists() else self.new_note(path, template)

    def create_person(self, name: str) -> Note | None:
        return self._create_master_note("persons", name, "person.md")

    def create_topic(self, name: str) -> Note | None:
        note = self._create_master_note("topics", name, "topic.md")
        # "Ponyfreizeit - Küche" ist ein Unterthema von "Ponyfreizeit"
        if note and " - " in name:
            note.props["oberthema"] = f"[[{name.split(' - ', 1)[0].strip()}]]"
            note.save()
        return note

    def _create_master_note(self, key: str, name: str, template: str) -> Note | None:
        path = self.folder(key) / f"{safe_filename(name)}.md"
        if path.exists():
            return None
        note = self.new_note(path, template)
        note.save()
        log.info("Neu angelegt: %s", path.relative_to(self.root))
        return note

    def add_alias(self, key: str, target: str, alias: str) -> bool:
        """Trägt 'alias' in die aliases-Property der Notiz 'target' ein."""
        target = strip_link(target)
        for note in self.notes(key):
            if normalize_name(note.name) == normalize_name(target):
                aliases = note.props.get("aliases") or []
                if not isinstance(aliases, list):
                    aliases = [aliases]
                if normalize_name(alias) not in {normalize_name(str(a)) for a in aliases}:
                    aliases.append(alias)
                note.props["aliases"] = aliases
                note.save()
                return True
        return False
