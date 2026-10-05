"""Google-Docs-Export (Datei -> Herunterladen -> Markdown) in Protokollnotizen übernehmen.

Jeder Abschnitt, der mit einem Datum TT.MM.JJJJ am Zeilenanfang beginnt, wird zur
Notiz ``Protokolle/JJJJ-MM-TT.md``. Der Protokolltext steht dort zwischen den
Auto-Markern und wird bei jedem Import aktualisiert. Alles außerhalb gehört den
Menschen. Eingebettete Bilder werden als Dateien in Protokolle/Anhänge/ gespeichert.

Später, wenn direkt in Obsidian protokolliert wird, entfällt dieser Schritt einfach.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ...core.extraction import ProtocolText
from ...core.vault import Vault

log = logging.getLogger(__name__)

TEMPLATE = "protocol.md"

# Datumszeile – erlaubt "# 21.11.2025", "**05.09.2025:**", "02\.10\.2026"
_DATE_LINE_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*\*|__)?(\d{1,2})\\?\.(\d{1,2})\\?\.(\d{4})\s*:?(?:\*\*|__)?\s*:?\s*(.*)$")
# Von Google ans Dateiende gehängte Bilder: [image1]: <data:image/png;base64,....>
_IMAGE_DEF_RE = re.compile(r"^\[(image\d+)\]:\s*<?data:image/(\w+);base64,([A-Za-z0-9+/=\s]+?)>?\s*$", re.M)
_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\[(image\d+)\]")
_EMBED_RE = re.compile(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)")


@dataclass
class _Section:
    date: date
    lines: list[str] = field(default_factory=list)


def import_export(vault: Vault, export_path: Path) -> int:
    """Übernimmt alle Protokolle aus dem Export. Gibt die Anzahl geänderter Notizen zurück."""
    text = export_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text, images = _extract_images(text, vault.attachments_dir)
    sections = _split_by_date(text)
    log.info("Export gelesen: %d Protokolle, %d Bilder", len(sections), len(images))

    changed = 0
    for section in sections:
        body = _IMAGE_REF_RE.sub(lambda m: f"![[{images[m.group(1)]}]]" if m.group(1) in images
                                 else m.group(0), "\n".join(section.lines))
        body = re.sub(r"\n{3,}", "\n\n", body).strip("\n")
        path = vault.folder("protocols") / f"{section.date.isoformat()}.md"
        note = vault.load_or_new(path, TEMPLATE)
        if not note.set_auto_block(body):
            log.warning("%s: Auto-Marker fehlen – Protokolltext nicht aktualisiert.", path.name)
            continue
        changed += note.save()
    return changed


def load_protocols(vault: Vault) -> list[ProtocolText]:
    """Alle Protokollnotizen mit Inhalt – das ist die Eingabe für die Extraktion."""
    protocols = []
    for note in vault.notes("protocols"):
        try:
            day = date.fromisoformat(note.name)
        except ValueError:
            continue
        text = _EMBED_RE.sub("", note.get_auto_block()).strip()
        if text:
            protocols.append(ProtocolText(name=note.name, date=day, text=text))
    return sorted(protocols, key=lambda p: p.date)


def _split_by_date(text: str) -> list[_Section]:
    sections: dict[date, _Section] = {}
    current: _Section | None = None
    for line in text.splitlines():
        match = _DATE_LINE_RE.match(line) if not line[:1].isspace() else None
        day = _to_date(match) if match else None
        if day:
            current = sections.setdefault(day, _Section(day))   # gleiches Datum doppelt -> zusammenfügen
            rest = match.group(4).strip()
            if rest.strip("*_ "):
                current.lines.append(rest)
            continue
        if current is not None:            # alles vor dem ersten Datum (Titel) wird übersprungen
            current.lines.append(line)
    return list(sections.values())


def _to_date(match: re.Match) -> date | None:
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _extract_images(text: str, folder: Path) -> tuple[str, dict[str, str]]:
    """Speichert Bilder unter einem Namen aus ihrem Inhalt (gleiches Bild = gleicher Name)."""
    images: dict[str, str] = {}
    for match in _IMAGE_DEF_RE.finditer(text):
        data = base64.b64decode(re.sub(r"\s", "", match.group(3)))
        ext = match.group(2).lower().replace("jpeg", "jpg")
        filename = f"bild-{hashlib.sha1(data).hexdigest()[:10]}.{ext}"
        path = folder / filename
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        images[match.group(1)] = filename
    return _IMAGE_DEF_RE.sub("", text), images
