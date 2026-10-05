"""Properties einer Besprechungsnotiz (Protokolle/JJJJ-MM-TT.md).

Englische Namen im Code, deutsche Property-Namen im Vault (``alias=…``).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class MeetingProperties(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = Field("besprechung", alias="typ")
    kind: str = Field("besprechung", alias="art")
    title: str = Field(alias="titel")
    date: dt.date = Field(alias="datum")
    status: str = Field(alias="status")     # stattgefunden | angekündigt | abgesagt | ausgefallen
    time: str | None = Field(None, alias="uhrzeit")
    location: str | None = Field(None, alias="ort")
    notes: list[str] = Field(default_factory=list, alias="hinweise")
    sources: list[str] = Field(default_factory=list, alias="quellen")

    def to_frontmatter(self) -> dict:
        return self.model_dump(by_alias=True)
