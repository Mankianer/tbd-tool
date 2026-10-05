"""Terminnotizen im Ordner Termine/ schreiben.

- Jede Terminnotiz hat eine stabile ``id``. Darüber wird sie wiedergefunden,
  auch wenn jemand die Datei umbenennt.
- Properties werden über den ``ManagedWriter`` geschrieben (Handeingaben bleiben).
- Der Abschnitt zwischen den Auto-Markern listet die Zitate aus den Protokollen.
- Löscht jemand eine Terminnotiz, wird sie nicht wieder angelegt.
- "Verwaiste" Termine (das Tool würde sie nicht mehr erzeugen) werden gelöscht,
  wenn niemand sie bearbeitet hat – sonst landen sie im Prüfbericht.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...core.managed import ManagedWriter, RunDecisions
from ...core.names import safe_filename
from ...core.notes import Note
from ...core.review import Option, Review, ReviewItem
from ...core.state import IgnoreList, State
from ...core.vault import Vault
from .builder import Appointment

log = logging.getLogger(__name__)

ID_PREFIX = "termin-"
TEMPLATE = "appointment.md"


def write_appointments(
    vault: Vault,
    appointments: list[Appointment],
    writer: ManagedWriter,
    state: State,
    review: Review,
    ignored: IgnoreList,
    decisions: RunDecisions,
    handle_orphans: bool,
    restore_deleted: bool = False,
) -> dict[str, int]:
    stats = {"neu": 0, "geändert": 0, "gelöscht": 0}
    existing = vault.notes_by_id("appointments")
    taken_paths = {n.path for n in existing.values()}

    for appointment in appointments:
        note_id = appointment.note_id
        entry = state.get(note_id)
        if entry and entry.get("deleted") and not restore_deleted:
            continue

        note = existing.get(note_id)
        if note is None and entry and entry.get("path") and not entry.get("deleted"):
            # Das Tool hat die Notiz schon einmal angelegt, sie ist aber weg -> vom Nutzer gelöscht
            if not restore_deleted:
                entry["deleted"] = True
                log.info("Termin wurde im Vault gelöscht und wird nicht neu angelegt: %s", entry["path"])
                continue

        is_new = note is None
        if is_new:
            path = _free_path(vault.folder("appointments"), _filename(appointment), taken_paths)
            taken_paths.add(path)
            note = vault.new_note(path, TEMPLATE)
            state.entry(note_id).pop("deleted", None)

        writer.write(note, note_id, appointment.properties())
        note.set_auto_block(_mentions_markdown(appointment))
        if note.save():
            stats["neu" if is_new else "geändert"] += 1

    if handle_orphans:
        produced = {a.note_id for a in appointments}
        stats["gelöscht"] = _handle_orphans(vault, existing, produced, writer, state, review,
                                            ignored, decisions)
    return stats


def _handle_orphans(vault: Vault, existing: dict[str, Note], produced: set[str], writer: ManagedWriter,
                    state: State, review: Review, ignored: IgnoreList, decisions: RunDecisions) -> int:
    deleted = 0
    for note_id in state.ids_with_prefix(ID_PREFIX):
        if note_id in produced or state.notes[note_id].get("deleted"):
            continue
        note = existing.get(note_id)
        if note is None:                       # Datei gibt es nicht mehr -> Eintrag aufräumen
            state.remove(note_id)
            continue
        item_id = f"orphan:{note_id}"
        if writer.is_untouched(note, note_id) or item_id in decisions.deletions:
            note.path.unlink()
            state.remove(note_id)
            deleted += 1
            if item_id in decisions.deletions:
                decisions.done.append(f"Verwaisten Termin gelöscht: {note.name}")
        elif item_id not in ignored:
            review.add(ReviewItem(
                id=item_id,
                title=note.link,
                details=["Kein Protokoll erwähnt diesen Termin mehr (z.B. weil ein Thema umbenannt wurde "
                         "oder ein Datum korrigiert ist). Die Notiz wurde von Hand bearbeitet."],
                options=[Option("delete", "Notiz löschen"), Option("ignore", "Behalten")],
            ))
    return deleted


def _mentions_markdown(appointment: Appointment) -> str:
    lines = []
    for mention in appointment.mentions:
        quote = " ".join(mention.quote.split())
        lines.append(f"- [[{mention.protocol}]]: „{quote}“" if quote else f"- [[{mention.protocol}]]")
    return "\n".join(dict.fromkeys(lines))


def _filename(appointment: Appointment) -> str:
    prefix = appointment.date.isoformat() if appointment.date else "ohne Datum"
    return safe_filename(f"{prefix} {appointment.title}")


def _free_path(folder: Path, stem: str, taken: set[Path]) -> Path:
    path, number = folder / f"{stem}.md", 2
    while path in taken or path.exists():
        path, number = folder / f"{stem} ({number}).md", number + 1
    return path
