"""Aus den Rohdaten aller Protokolle die eigentlichen Termine bauen.

Ablauf für jede Erwähnung (ExtractedAppointment):
  1. Datum und Uhrzeit auflösen          (core/dates.py)
  2. Thema und Personen auflösen          (features/master_data.py)
  3. Zitat gegen das Protokoll prüfen     (erfundene Termine erkennen)
  4. Mit anderen Erwähnungen desselben Termins zusammenführen

Zwei Erwähnungen gelten hier als derselbe Termin, wenn Art, Datum und Hauptthema
gleich sind (siehe ``Appointment.key``). Spätere Protokolle haben Vorrang.
Was danach noch doppelt ist (z.B. andere Art am selben Tag), fasst ``dedupe.py`` zusammen.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from ...core.dates import normalize_time, resolve_date
from ...core.extraction import ProtocolText
from ...core.names import normalize_name
from ...core.review import Option, Review, ReviewItem
from ...core.state import IgnoreList
from ..master_data import Resolver
from .models import AppointmentExtraction, AppointmentProperties, ExtractedAppointment

MEETING = "besprechung"


@dataclass
class Mention:
    protocol: str          # Name der Protokollnotiz, z.B. "2026-09-18"
    quote: str


@dataclass
class Appointment:
    key: str
    kind: str
    title: str
    status: str
    date: date | None = None
    date_end: date | None = None
    time: str | None = None
    time_end: str | None = None
    location: str | None = None
    topic: str | None = None
    topic_key: str = ""            # normalisiertes Hauptthema, zum Vergleichen
    responsible: list[str] = field(default_factory=list)
    involved: list[str] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)

    @property
    def note_id(self) -> str:
        return "termin-" + hashlib.sha1(self.key.encode()).hexdigest()[:10]

    @property
    def sources(self) -> list[str]:
        return list(dict.fromkeys(f"[[{m.protocol}]]" for m in self.mentions))

    def properties(self) -> dict:
        return AppointmentProperties(
            kind=self.kind, title=self.title, date=self.date, date_end=self.date_end,
            time=self.time, time_end=self.time_end, location=self.location, status=self.status,
            topic=self.topic, responsible=self.responsible, involved=self.involved,
            sources=self.sources,
        ).to_frontmatter()

    def merge(self, newer: "Appointment") -> None:
        """Übernimmt Angaben einer späteren Erwähnung (leere Angaben überschreiben nichts)."""
        for attr in ("kind", "title", "status", "date_end", "time", "time_end", "location", "topic"):
            value = getattr(newer, attr)
            if value:
                setattr(self, attr, value)
        self.responsible = _union(self.responsible, newer.responsible)
        self.involved = [p for p in _union(self.involved, newer.involved) if p not in self.responsible]
        self.mentions += newer.mentions


@dataclass
class BuildResult:
    appointments: list[Appointment]   # Termine für den Ordner Termine/
    meetings: list[Appointment]       # Hinweise auf kommende Freitagsbesprechungen


def build_appointments(
    protocols: list[ProtocolText],
    results: dict[str, AppointmentExtraction],
    resolver: Resolver,
    review: Review,
    ignored: IgnoreList,
) -> BuildResult:
    merged: dict[str, Appointment] = {}
    for protocol in sorted(protocols, key=lambda p: p.date):
        result = results.get(protocol.name)
        if result is None:
            continue
        for raw in result.appointments:
            appointment = _from_mention(raw, protocol, resolver, review, ignored)
            if appointment is None:
                continue
            if appointment.key in merged:
                merged[appointment.key].merge(appointment)
            else:
                merged[appointment.key] = appointment

    everything = sorted(merged.values(), key=lambda a: (a.date or date.max, a.title))
    return BuildResult(
        appointments=[a for a in everything if a.kind != MEETING],
        meetings=[a for a in everything if a.kind == MEETING],
    )


def _from_mention(raw: ExtractedAppointment, protocol: ProtocolText, resolver: Resolver,
                  review: Review, ignored: IgnoreList) -> Appointment | None:
    start = resolve_date(raw.date_text, raw.date, protocol.date)
    end = resolve_date(raw.date_end_text, raw.date_end, start.value) if start.value and (
        raw.date_end_text or raw.date_end) else None
    end_date = end.value if end and end.value and end.value > start.value else None

    # Die Besprechung, die das Protokoll selbst beschreibt, ist kein eigener Termin
    if raw.kind == MEETING and start.value == protocol.date:
        return None

    # Ein Hinweis pro Termin genügt – das Enddatum nur melden, wenn der Start unauffällig war
    warning = start.warning or (end.warning if end else None)
    if warning:
        _hint(review, ignored, protocol, raw, warning)
    if not _quote_found(raw.quote, protocol.text):
        _hint(review, ignored, protocol, raw,
              "Zitat nicht im Protokoll gefunden – der Termin könnte vom Modell erfunden sein.")

    topic, topic_key = resolver.topic(raw.topic, raw.subtopic, protocol.name)
    responsible = _unique(resolver.person(p, protocol.name) for p in raw.responsible)
    involved = [p for p in _unique(resolver.person(p, protocol.name) for p in raw.involved)
                if p not in responsible]

    when = start.value.isoformat() if start.value else "ohne-datum:" + normalize_name(raw.title)
    return Appointment(
        key=f"{raw.kind}|{when}|{topic_key}",
        kind=raw.kind,
        title=raw.title.strip(),
        status=raw.status,
        date=start.value,
        date_end=end_date,
        time=normalize_time(raw.time),
        time_end=normalize_time(raw.time_end),
        location=raw.location.strip() or None,
        topic=topic,
        topic_key=topic_key,
        responsible=responsible,
        involved=involved,
        mentions=[Mention(protocol.name, raw.quote.strip())],
    )


def _hint(review: Review, ignored: IgnoreList, protocol: ProtocolText,
          raw: ExtractedAppointment, message: str) -> None:
    digest = hashlib.sha1(f"{raw.title}|{raw.quote}|{message}".encode()).hexdigest()[:8]
    item_id = f"hint:{protocol.name}:{digest}"
    if item_id in ignored:
        return
    review.add(ReviewItem(
        id=item_id,
        title=f"{raw.title} ({protocol.name})",
        details=[message, f"Zitat: „{raw.quote}“" if raw.quote else "Kein Zitat angegeben."],
        options=[Option("ignore", "Gesehen – nicht mehr anzeigen")],
    ), occurrence=protocol.name)


def _quote_found(quote: str, text: str) -> bool:
    """Prüft großzügig, ob das Zitat im Protokoll steht (Formatierung egal, 80 % der Wörter)."""
    quote_n, text_n = _plain(quote), _plain(text)
    if not quote_n:
        return False
    if quote_n in text_n:
        return True
    words = [w for w in quote_n.split() if len(w) > 2]
    text_words = set(text_n.split())
    return bool(words) and sum(w in text_words for w in words) / len(words) >= 0.8


def _plain(text: str) -> str:
    text = re.sub(r"[*_`#>\\\[\]]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _unique(items) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def _union(a: list[str], b: list[str]) -> list[str]:
    return list(dict.fromkeys(a + b))
