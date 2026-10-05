"""Datenmodelle für Termine.

``ExtractedAppointment`` – was das Modell pro Erwähnung liefert (JSON, englische Feldnamen).
``AppointmentProperties`` – die Obsidian-Properties einer Terminnotiz. Hier steht
an EINER Stelle, wie die englischen Namen im Code den deutschen Property-Namen
im Vault entsprechen (``alias=…``).
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["veranstaltung", "treffen", "deadline", "besprechung"]
Status = Literal["vorschlag", "geplant", "bestätigt", "verschoben", "abgesagt"]


# --- Antwort des Modells -------------------------------------------------------

class ExtractedAppointment(BaseModel):
    title: str
    kind: Kind
    date_text: str = ""        # Datum genau wie im Protokoll geschrieben
    date: str = ""             # Vorschlag des Modells: JJJJ-MM-TT
    date_end_text: str = ""
    date_end: str = ""
    time: str = ""
    time_end: str = ""
    location: str = ""
    status: Status = "geplant"
    topic: str = ""
    subtopic: str = ""
    responsible: list[str] = Field(default_factory=list)
    involved: list[str] = Field(default_factory=list)
    quote: str = ""


class AppointmentExtraction(BaseModel):
    appointments: list[ExtractedAppointment] = Field(default_factory=list)


# --- Properties einer Terminnotiz ------------------------------------------------

class AppointmentProperties(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = Field("termin", alias="typ")
    kind: str = Field(alias="art")
    title: str = Field(alias="titel")
    date: dt.date | None = Field(None, alias="datum")
    date_end: dt.date | None = Field(None, alias="datum_bis")
    time: str | None = Field(None, alias="uhrzeit")
    time_end: str | None = Field(None, alias="uhrzeit_bis")
    location: str | None = Field(None, alias="ort")
    status: str = Field("geplant", alias="status")
    topic: str | None = Field(None, alias="thema")
    responsible: list[str] = Field(default_factory=list, alias="zustaendig")
    involved: list[str] = Field(default_factory=list, alias="beteiligt")
    sources: list[str] = Field(default_factory=list, alias="quellen")

    def to_frontmatter(self) -> dict:
        return self.model_dump(by_alias=True)

