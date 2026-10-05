"""Lesen und Schreiben einzelner Markdown-Notizen (YAML-Frontmatter + Text).

Eine Notiz besteht aus
  - ``props``:  den Obsidian-Properties (Frontmatter) als dict
  - ``body``:   dem Text darunter

Teile des Textes, die das Tool verwaltet, stehen zwischen den Markern
AUTO_START und AUTO_END. Alles außerhalb davon gehört den Menschen und wird
nie verändert.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

AUTO_START = "<!-- tbd:auto:start -->"
AUTO_END = "<!-- tbd:auto:end -->"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n?---[ \t]*(?:\n|\Z)", re.S)
_AUTO_RE = re.compile(re.escape(AUTO_START) + r"\n?(.*?)\n?" + re.escape(AUTO_END), re.S)


# --- YAML-Einstellungen --------------------------------------------------------
# PyYAML liest "17:00" standardmäßig als Zahl (1020, Sexagesimal aus YAML 1.1).
# Obsidian schreibt Uhrzeiten aber ohne Anführungszeichen. Deshalb ein eigener
# Loader, der nur "normale" Zahlen als Zahlen erkennt.

class _Loader(yaml.SafeLoader):
    pass


_Loader.yaml_implicit_resolvers = {
    key: [r for r in resolvers if r[0] not in ("tag:yaml.org,2002:int", "tag:yaml.org,2002:float")]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^[-+]?(0|[1-9][0-9]*)$"), list("-+0123456789"))
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float", re.compile(r"^[-+]?[0-9]*\.[0-9]+$"), list("-+0123456789."))


class _Dumper(yaml.SafeDumper):
    pass


# Leere Werte als "key:" statt "key: null" schreiben – so zeigt Obsidian ein leeres Feld.
_Dumper.add_representer(type(None), lambda dumper, _: dumper.represent_scalar("tag:yaml.org,2002:null", ""))


def dump_yaml(data: dict) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False)


def load_yaml(text: str):
    return yaml.load(text, Loader=_Loader)


# --- Notiz -------------------------------------------------------------------

@dataclass
class Note:
    path: Path
    props: dict = field(default_factory=dict)
    body: str = ""
    _original: tuple[dict, str] | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        """Name der Notiz, wie er in [[Wikilinks]] verwendet wird."""
        return self.path.stem

    @property
    def link(self) -> str:
        return f"[[{self.name}]]"

    # -- Laden / Speichern --

    @classmethod
    def parse(cls, path: Path, text: str) -> "Note":
        text = text.replace("\r\n", "\n")
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return cls(path=path, props={}, body=text)
        try:
            props = load_yaml(match.group(1)) or {}
        except yaml.YAMLError as err:
            raise ValueError(f"Frontmatter in {path} ist kein gültiges YAML: {err}") from err
        if not isinstance(props, dict):
            props = {}
        return cls(path=path, props=props, body=text[match.end():])

    @classmethod
    def load(cls, path: Path) -> "Note":
        note = cls.parse(path, path.read_text(encoding="utf-8"))
        note._original = (copy.deepcopy(note.props), note.body)
        return note

    def render(self) -> str:
        if not self.props:
            return self.body
        return f"---\n{dump_yaml(self.props)}---\n{self.body}"

    def save(self) -> bool:
        """Schreibt die Notiz – aber nur, wenn sich inhaltlich etwas geändert hat.

        Gibt True zurück, wenn geschrieben wurde. So bleiben unveränderte Dateien
        unangetastet (wichtig für Synchronisation und Git).
        """
        if self._original == (self.props, self.body):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.render(), encoding="utf-8")
        self._original = (copy.deepcopy(self.props), self.body)
        return True

    # -- Vom Tool verwalteter Textbereich --

    def has_auto_block(self) -> bool:
        return bool(_AUTO_RE.search(self.body))

    def get_auto_block(self) -> str:
        match = _AUTO_RE.search(self.body)
        return match.group(1).strip("\n") if match else ""

    def set_auto_block(self, content: str) -> bool:
        """Ersetzt den Inhalt zwischen den Auto-Markern.

        Fehlen die Marker (z.B. weil jemand sie gelöscht hat), wird nichts
        geändert und False zurückgegeben.
        """
        if not self.has_auto_block():
            return False
        block = f"{AUTO_START}\n{content.strip()}\n{AUTO_END}" if content.strip() else f"{AUTO_START}\n{AUTO_END}"
        self.body = _AUTO_RE.sub(lambda _: block, self.body, count=1)
        return True
