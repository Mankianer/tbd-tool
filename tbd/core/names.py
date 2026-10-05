"""Namen vergleichen und über Aliase auflösen.

Ein ``NameIndex`` kennt alle Notizen eines Ordners (z.B. Personen) samt ihrer
``aliases``-Property und beantwortet die Frage: "Welche Notiz ist mit 'Mitch'
gemeint?" – Groß-/Kleinschreibung, Akzente und Satzzeichen spielen dabei keine
Rolle (René = Rene = rene).
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from .notes import Note


def normalize_name(text: str) -> str:
    """'René ' -> 'rene', 'Ann-Cathrin' -> 'ann cathrin'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w]+", " ", text.lower())
    return text.strip()


def safe_filename(text: str) -> str:
    """Entfernt Zeichen, die in Dateinamen oder Obsidian-Links nicht erlaubt sind."""
    text = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", text)
    return re.sub(r"\s+", " ", text).strip(" .") or "Unbenannt"


def as_link(name: str) -> str:
    return f"[[{name}]]"


def strip_link(value: str) -> str:
    """'[[Pia]]' -> 'Pia', '[[Pia|P.]]' -> 'Pia', 'Pia' -> 'Pia'."""
    match = re.fullmatch(r"\s*\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]\s*", value or "")
    return match.group(1).strip() if match else (value or "").strip()


class NameIndex:
    """Zuordnung von Namen und Aliasen zu Notiznamen."""

    def __init__(self, notes: list[Note]):
        self._lookup: dict[str, str] = {}
        self.aliases: dict[str, list[str]] = {}
        for note in notes:
            self._lookup[normalize_name(note.name)] = note.name
            self.aliases[note.name] = _as_list(note.props.get("aliases"))
        # Aliase erst danach eintragen, damit echte Notiznamen Vorrang haben
        for name, aliases in self.aliases.items():
            for alias in aliases:
                self._lookup.setdefault(normalize_name(alias), name)

    @property
    def names(self) -> list[str]:
        return sorted(self.aliases)

    def resolve(self, raw: str) -> str | None:
        """Gibt den Notiznamen zurück oder None, wenn der Name unbekannt ist."""
        return self._lookup.get(normalize_name(strip_link(raw)))

    def suggest(self, raw: str) -> str | None:
        """Ähnlichster bekannter Name (für Vorschläge im Prüfbericht)."""
        matches = difflib.get_close_matches(normalize_name(raw), list(self._lookup), n=1, cutoff=0.75)
        return self._lookup[matches[0]] if matches else None

    def describe(self) -> list[str]:
        """'Michelle (Mitch)' – für den Prompt."""
        return [f"{n} ({', '.join(a)})" if a else n for n, a in sorted(self.aliases.items())]


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]
