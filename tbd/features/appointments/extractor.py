"""Extraktor für Termine – verbindet Prompt-Datei und Datenmodell."""

from __future__ import annotations

from pathlib import Path

from ...core.extraction import ExtractionContext, Extractor, ProtocolText
from ...core.names import normalize_name
from .models import AppointmentExtraction

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


class AppointmentExtractor(Extractor):
    name = "appointments"
    version = 1                     # hochzählen, wenn sich die Auswertung grundlegend ändert
    result_model = AppointmentExtraction
    prompt_file = Path(__file__).with_name("prompt.md")

    def fill_prompt(self, template: str, protocol: ProtocolText, context: ExtractionContext) -> str:
        values = {
            "protocol_date": protocol.date.strftime("%d.%m.%Y"),
            "protocol_weekday": WEEKDAYS[protocol.date.weekday()],
            "known_topics": _bullet_list(context.known_topics),
            "known_persons": _bullet_list(context.known_persons),
        }
        for key, value in values.items():
            template = template.replace("{{" + key + "}}", value)
        return template

    def learn(self, result: AppointmentExtraction, context: ExtractionContext) -> None:
        known = {normalize_name(t.split(" (")[0]) for t in context.known_topics}
        for appointment in result.appointments:
            topic = appointment.topic.strip()
            if topic and normalize_name(topic) not in known:
                context.known_topics.append(topic)
                known.add(normalize_name(topic))


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "(noch keine)"
