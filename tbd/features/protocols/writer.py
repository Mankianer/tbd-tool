"""Properties der Besprechungsnotizen (Protokolle/JJJJ-MM-TT.md) pflegen.

Jede Freitagsbesprechung ist selbst ein Termin. Status-Regeln:
  - Protokoll vorhanden                         -> stattgefunden
  - angekündigt, aber explizit abgesagt         -> abgesagt
  - angekündigt, Datum vorbei, kein Protokoll   -> ausgefallen
  - angekündigt, Datum in der Zukunft           -> angekündigt

Hinweise aus früheren Protokollen (anderer Ort, andere Uhrzeit …) landen in
den Properties ``ort``, ``uhrzeit`` und ``hinweise`` der Besprechungsnotiz.
"""

from __future__ import annotations

from datetime import date

from ...core.extraction import ProtocolText
from ...core.managed import ManagedWriter
from ...core.vault import Vault
from ..appointments.builder import Appointment
from .models import MeetingProperties

TEMPLATE = "protocol.md"


def write_meeting_notes(
    vault: Vault,
    protocols: list[ProtocolText],
    announcements: list[Appointment],
    writer: ManagedWriter,
    today: date,
) -> int:
    with_text = {p.date for p in protocols}
    by_date: dict[date, list[Appointment]] = {}
    for announcement in announcements:
        if announcement.date:
            by_date.setdefault(announcement.date, []).append(announcement)

    changed = 0
    for day in sorted(with_text | set(by_date)):
        notes_for_day = by_date.get(day, [])
        path = vault.folder("protocols") / f"{day.isoformat()}.md"
        note = vault.load_or_new(path, TEMPLATE)
        props = MeetingProperties(
            title=f"Besprechung {day:%d.%m.%Y}",
            date=day,
            status=_status(day, day in with_text, notes_for_day, today),
            time=_latest(a.time for a in notes_for_day),
            location=_latest(a.location for a in notes_for_day),
            notes=list(dict.fromkeys(m.quote for a in notes_for_day for m in a.mentions if m.quote)),
            sources=list(dict.fromkeys(s for a in notes_for_day for s in a.sources)),
        )
        writer.write(note, f"besprechung-{day.isoformat()}", props.to_frontmatter())
        changed += note.save()
    return changed


def _status(day: date, has_protocol: bool, announcements: list[Appointment], today: date) -> str:
    if has_protocol:
        return "stattgefunden"
    if announcements and announcements[-1].status == "abgesagt":
        return "abgesagt"
    return "ausgefallen" if day < today else "angekündigt"


def _latest(values) -> str | None:
    found = [v for v in values if v]
    return found[-1] if found else None
