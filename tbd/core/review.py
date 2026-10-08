"""Der Prüfbericht (_System/Prüfbericht.md).

Der Bericht wird bei jedem Lauf komplett neu erzeugt – er ist also kein
Speicher, sondern nur eine Ansicht auf alles, was gerade unklar ist.
Dauerhaft gespeichert werden nur die *Entscheidungen*:
  - "Neue Person / Alias"   -> direkt als Notiz bzw. aliases-Property im Vault
  - "Ignorieren"            -> .tbd/ignored.yaml
  - Konflikt / Löschen      -> wird im selben Lauf umgesetzt

Aufbau eines Eintrags im Markdown:

    ### Kira
    %% id: person:kira %%
    Vorkommen: [[2026-06-12]]
    - [ ] Neue Person anlegen %% action: create %%
    - [ ] Alias von [[Bellis]] %% action: alias %%
    - [ ] Ignorieren %% action: ignore %%

``%% … %%`` sind Obsidian-Kommentare: im Lesemodus unsichtbar, aber für das
Tool lesbar. Die Zeile "Alias von [[…]]" darf man vor dem Anhaken anpassen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Reihenfolge und Überschriften der Abschnitte. Der Schlüssel ist der Präfix der Item-Id.
SECTIONS = {
    "person": "Neue Personen",
    "topic": "Neue Themen",
    "duplicate": "Mögliche doppelte Termine",
    "conflict": "Konflikte (Handeingabe vs. Protokoll)",
    "orphan": "Verwaiste Termine",
    "hint": "Hinweise",
}
MAX_OCCURRENCES = 8


@dataclass
class Option:
    action: str          # z.B. "create", "alias", "ignore", "accept", "delete"
    label: str           # Text hinter der Checkbox


@dataclass
class ReviewItem:
    id: str              # eindeutig und stabil, z.B. "person:kira"; Präfix = Abschnitt
    title: str
    details: list[str] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    occurrences: list[str] = field(default_factory=list)   # Namen von Protokollnotizen

    @property
    def kind(self) -> str:
        return self.id.split(":", 1)[0]


@dataclass
class Decision:
    item_id: str
    title: str
    action: str
    target: str | None   # bei "alias": Name aus dem [[Link]] der Zeile

    @property
    def kind(self) -> str:
        return self.item_id.split(":", 1)[0]


class Review:
    def __init__(self, done: list[str] | None = None):
        self.items: dict[str, ReviewItem] = {}
        self.done: list[str] = list(done or [])

    def add(self, item: ReviewItem, occurrence: str | None = None) -> None:
        """Fügt einen Eintrag hinzu – gleiche Id wird zusammengefasst."""
        existing = self.items.setdefault(item.id, item)
        if occurrence and occurrence not in existing.occurrences:
            existing.occurrences.append(occurrence)
        for detail in item.details:
            if detail not in existing.details:
                existing.details.append(detail)

    def render(self, now: datetime | None = None) -> str:
        now = now or datetime.now()
        lines = [
            "# Prüfbericht",
            "",
            f"Stand: {now:%d.%m.%Y %H:%M} · {len(self.items)} offene Punkte",
            "",
            "> [!info] So funktioniert's",
            "> Bei jedem Punkt **eine** Option anhaken und danach `tbd apply` ausführen "
            "(oder einfach beim nächsten `tbd sync`). Bei „Alias von [[…]]“ kann der Name im Link "
            "vorher angepasst werden. Wer ein Problem direkt in der Notiz löst, braucht nichts anzuhaken.",
            "",
        ]
        if not self.items:
            lines += ["Keine offenen Punkte 🎉", ""]
        for prefix, heading in SECTIONS.items():
            items = [i for i in self.items.values() if i.kind == prefix]
            if not items:
                continue
            lines += [f"## {heading} ({len(items)})", ""]
            for item in sorted(items, key=lambda i: i.title.lower()):
                lines += _render_item(item)
        if self.done:
            lines += ["## Zuletzt erledigt", ""] + [f"- {d}" for d in self.done] + [""]
        return "\n".join(lines)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")


def _render_item(item: ReviewItem) -> list[str]:
    lines = [f"### {item.title}", f"%% id: {item.id} %%"]
    lines += item.details
    if item.occurrences:
        shown = ", ".join(f"[[{o}]]" for o in sorted(item.occurrences)[:MAX_OCCURRENCES])
        more = len(item.occurrences) - MAX_OCCURRENCES
        lines.append(f"Vorkommen: {shown}" + (f" und {more} weitere" if more > 0 else ""))
    lines += [f"- [ ] {o.label} %% action: {o.action} %%" for o in item.options]
    return lines + [""]


# --- Entscheidungen aus einem ausgefüllten Bericht lesen -----------------------

_HEADING_RE = re.compile(r"^###\s+(.*?)\s*$")
_ID_RE = re.compile(r"^%%\s*id:\s*(.+?)\s*%%\s*$")
_CHECKED_RE = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+(.*?)\s*%%\s*action:\s*(\w+)\s*%%\s*$")
_LINK_RE = re.compile(r"\[\[([^\]|#]+)")


def parse_decisions(text: str) -> list[Decision]:
    decisions: list[Decision] = []
    title, item_id = "", None
    for line in text.splitlines():
        if m := _HEADING_RE.match(line):
            title, item_id = m.group(1), None
        elif m := _ID_RE.match(line.strip()):
            item_id = m.group(1)
        elif item_id and (m := _CHECKED_RE.match(line)):
            link = _LINK_RE.search(m.group(1))
            target = link.group(1).strip() if link else None
            decisions.append(Decision(item_id=item_id, title=title, action=m.group(2), target=target))
    return decisions


def read_decisions(path: Path) -> list[Decision]:
    if not path.exists():
        return []
    return parse_decisions(path.read_text(encoding="utf-8"))
