"""Allgemeiner Rahmen für LLM-Extraktoren (Termine, später Aufgaben, …).

Ein Extraktor legt nur fest:
  - ``name``          z.B. "appointments" (auch Name des Cache-Ordners)
  - ``version``       hochzählen, wenn sich Schema/Logik ändert -> Cache wird ungültig
  - ``result_model``  Pydantic-Modell der Antwort (daraus entsteht das JSON-Schema)
  - ``prompt_file``   Pfad zur Prompt-Datei (Markdown mit {{platzhaltern}})
  - ``fill_prompt``   setzt Protokoll-Infos in den Prompt ein

Alles andere – Cache, Ollama-Aufruf, Validierung, Wiederholung bei Fehlern –
erledigt ``run_extractor``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
import datetime as dt
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .llm import LLMError, OllamaClient

log = logging.getLogger(__name__)


@dataclass
class ProtocolText:
    name: str      # Name der Protokollnotiz, z.B. "2026-09-18"
    date: dt.date
    text: str


@dataclass
class ExtractionContext:
    """Wissen aus dem Vault, das dem Modell hilft (bekannte Themen und Personen)."""
    known_topics: list[str] = field(default_factory=list)
    known_persons: list[str] = field(default_factory=list)


class Extractor:
    name: str = ""
    version: int = 1
    result_model: type[BaseModel] = BaseModel
    prompt_file: Path

    def prompt_template(self) -> str:
        return self.prompt_file.read_text(encoding="utf-8")

    def fill_prompt(self, template: str, protocol: ProtocolText, context: ExtractionContext) -> str:
        raise NotImplementedError

    def schema(self) -> dict:
        return self.result_model.model_json_schema()

    def learn(self, result: BaseModel, context: ExtractionContext) -> None:
        """Optional: Wissen aus einem Ergebnis für die nächsten Protokolle merken
        (z.B. neu gefundene Themen, damit das Modell dieselbe Schreibweise wiederverwendet)."""


@dataclass
class ExtractionRun:
    results: dict[str, BaseModel] = field(default_factory=dict)   # Protokollname -> Ergebnis
    missing: list[str] = field(default_factory=list)              # Protokolle ohne Ergebnis

    @property
    def complete(self) -> bool:
        return not self.missing


class ExtractionCache:
    """Speichert Ergebnisse unter .tbd/cache/<extraktor>/<protokoll>.json.

    Der Schlüssel ist ein Hash aus Protokolltext, Prompt, Modell, Schema und
    Extraktor-Version. Ändert sich davon etwas, gilt der Eintrag als veraltet.
    Bekannte Themen/Personen gehen bewusst NICHT in den Schlüssel ein –
    sonst würde jede neue Person alle Protokolle neu extrahieren lassen.
    """

    def __init__(self, tool_dir: Path, extractor_name: str):
        self.dir = tool_dir / "cache" / extractor_name

    @staticmethod
    def make_key(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    def get(self, protocol_name: str, key: str) -> dict | None:
        path = self.dir / f"{protocol_name}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("result") if data.get("key") == key else None

    def put(self, protocol_name: str, key: str, result: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{protocol_name}.json"
        path.write_text(json.dumps({"key": key, "result": result}, ensure_ascii=False, indent=1),
                        encoding="utf-8")


def run_extractor(
    extractor: Extractor,
    protocols: list[ProtocolText],
    cache: ExtractionCache,
    model_name: str,
    context: ExtractionContext,
    llm: OllamaClient | None,
    refresh: bool = False,
) -> ExtractionRun:
    """Liefert für jedes Protokoll ein Ergebnis – aus dem Cache oder per LLM.

    Ist ``llm`` None (z.B. bei ``tbd apply``), wird nur der Cache benutzt.
    """
    run = ExtractionRun()
    template = extractor.prompt_template()
    schema = extractor.schema()
    schema_text = json.dumps(schema, sort_keys=True)

    todo: list[tuple[ProtocolText, str]] = []
    for protocol in protocols:
        key = cache.make_key(protocol.text, template, model_name, schema_text, str(extractor.version))
        cached = None if refresh else cache.get(protocol.name, key)
        if cached is not None:
            run.results[protocol.name] = extractor.result_model.model_validate(cached)
        else:
            todo.append((protocol, key))

    if not todo:
        return run
    if llm is None:
        run.missing = [p.name for p, _ in todo]
        log.warning("%d Protokoll(e) noch nicht extrahiert – dafür 'tbd sync' ausführen.", len(todo))
        return run

    llm.check()
    log.info("Extrahiere %s aus %d Protokoll(en) mit %s …", extractor.name, len(todo), llm.model)
    for number, (protocol, key) in enumerate(todo, start=1):
        started = time.monotonic()
        system = extractor.fill_prompt(template, protocol, context)
        result = _ask_with_retry(llm, extractor, system, protocol.text, schema)
        if result is None:
            run.missing.append(protocol.name)
            log.error("  [%d/%d] %s: fehlgeschlagen", number, len(todo), protocol.name)
            continue
        cache.put(protocol.name, key, result.model_dump(mode="json"))
        run.results[protocol.name] = result
        extractor.learn(result, context)
        log.info("  [%d/%d] %s: %s (%.0f s)", number, len(todo), protocol.name,
                 _summary(result), time.monotonic() - started)
    return run


def _ask_with_retry(llm: OllamaClient, extractor: Extractor, system: str, user: str,
                    schema: dict, attempts: int = 2) -> BaseModel | None:
    for attempt in range(1, attempts + 1):
        try:
            return extractor.result_model.model_validate(llm.chat_json(system, user, schema))
        except (LLMError, ValidationError) as err:
            log.warning("    Versuch %d/%d: %s", attempt, attempts, str(err).splitlines()[0])
    return None


def _summary(result: BaseModel) -> str:
    counts = [f"{len(v)} {k}" for k, v in result.model_dump().items() if isinstance(v, list)]
    return ", ".join(counts) or "ok"
