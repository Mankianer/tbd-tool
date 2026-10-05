"""Allgemeiner Rahmen für LLM-Extraktoren (Termine, später Aufgaben, …).

Ein Extraktor legt nur fest:
  - ``name``                z.B. "appointments" (auch Name des Cache-Ordners)
  - ``version``             hochzählen, wenn sich Schema/Logik ändert -> Cache wird ungültig
  - ``result_model``        Pydantic-Modell der Antwort (daraus entsteht das JSON-Schema)
  - ``system_prompt_file``  Anweisungen an das Modell – für alle Protokolle GLEICH
  - ``user_prompt_file``    Nachricht pro Protokoll mit {{platzhaltern}}
  - ``prompt_values``       liefert die Werte für die Platzhalter

Warum zwei Dateien? Ollama merkt sich den Anfang der letzten Anfrage. Ist die
System-Nachricht bei jedem Protokoll identisch, muss das Modell die langen
Anweisungen nur einmal verarbeiten statt bei jedem Protokoll neu. Deshalb gehört
alles, was sich ändert (Datum, bekannte Themen, Protokolltext), in die
Nutzer-Nachricht.

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
    system_prompt_file: Path
    user_prompt_file: Path

    def prompt_values(self, protocol: ProtocolText, context: ExtractionContext) -> dict[str, str]:
        """Werte für die {{platzhalter}} in der Nutzer-Nachricht."""
        raise NotImplementedError

    def load_prompts(self) -> tuple[str, str]:
        return (self.system_prompt_file.read_text(encoding="utf-8"),
                self.user_prompt_file.read_text(encoding="utf-8"))

    def user_message(self, template: str, protocol: ProtocolText, context: ExtractionContext) -> str:
        for key, value in self.prompt_values(protocol, context).items():
            template = template.replace("{{" + key + "}}", value)
        return template

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


@dataclass
class CacheEntry:
    result: dict
    model: str            # Modell, mit dem das Ergebnis erzeugt wurde
    prompt_hash: str      # Prompt-Stand, mit dem das Ergebnis erzeugt wurde
    migrated: bool = False


class ExtractionCache:
    """Speichert Ergebnisse unter .tbd/cache/<extraktor>/<protokoll>.json.

    Ein Eintrag gilt als gültig, solange sich nichts ändert, wodurch das
    Ergebnis nicht mehr passen kann:
      - ``text_hash``       der Protokolltext
      - ``structure_hash``  JSON-Schema und Extraktor-Version (Aufbau des Ergebnisses)

    Modell und Prompt werden nur VERMERKT, machen den Eintrag aber nicht ungültig.
    So kann man das Modell wechseln oder den Prompt verbessern, ohne dass alles
    neu ausgewertet werden muss. Neu auswerten geht gezielt mit ``--refresh``.

    Bekannte Themen/Personen fließen nirgends ein – sonst würde jede neue Person
    alle Protokolle neu extrahieren lassen.
    """

    FORMAT = 2

    def __init__(self, tool_dir: Path, extractor_name: str):
        self.dir = tool_dir / "cache" / extractor_name

    @staticmethod
    def make_hash(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    def _path(self, protocol_name: str) -> Path:
        return self.dir / f"{protocol_name}.json"

    def get(self, protocol_name: str, text_hash: str, structure_hash: str) -> CacheEntry | None:
        path = self._path(protocol_name)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if "result" not in data:
            return None
        if data.get("format") != self.FORMAT:
            # Altes Format (bis Version 0.1): Schlüssel nicht mehr prüfbar -> einmalig übernehmen
            return CacheEntry(result=data["result"], model="unbekannt", prompt_hash="", migrated=True)
        if data.get("text_hash") != text_hash or data.get("structure_hash") != structure_hash:
            return None
        return CacheEntry(result=data["result"], model=data.get("model", "unbekannt"),
                          prompt_hash=data.get("prompt_hash", ""))

    def put(self, protocol_name: str, entry: CacheEntry, text_hash: str, structure_hash: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {
            "format": self.FORMAT,
            "text_hash": text_hash,
            "structure_hash": structure_hash,
            "model": entry.model,
            "prompt_hash": entry.prompt_hash,
            "result": entry.result,
        }
        self._path(protocol_name).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                             encoding="utf-8")


def run_extractor(
    extractor: Extractor,
    protocols: list[ProtocolText],
    cache: ExtractionCache,
    model_name: str,
    context: ExtractionContext,
    llm: OllamaClient | None,
    refresh: bool | set[str] = False,
) -> ExtractionRun:
    """Liefert für jedes Protokoll ein Ergebnis – aus dem Cache oder per LLM.

    ``refresh``: True = alle Protokolle neu auswerten, eine Menge von
    Protokollnamen = nur diese, False = nur was nicht im Cache ist.
    Ist ``llm`` None (z.B. bei ``tbd apply``), wird nur der Cache benutzt.
    """
    run = ExtractionRun()
    system, user_template = extractor.load_prompts()
    schema = extractor.schema()
    structure_hash = cache.make_hash(json.dumps(schema, sort_keys=True), str(extractor.version))
    prompt_hash = cache.make_hash(system, user_template)
    outdated: list[str] = []    # aus dem Cache, aber mit anderem Modell oder Prompt erzeugt

    if isinstance(refresh, set):
        unknown = refresh - {p.name for p in protocols}
        if unknown:
            log.warning("--refresh: Protokoll(e) nicht gefunden: %s (Format: JJJJ-MM-TT)",
                        ", ".join(sorted(unknown)))

    todo: list[tuple[ProtocolText, str]] = []
    for protocol in protocols:
        text_hash = cache.make_hash(protocol.text)
        wants_refresh = refresh is True or (isinstance(refresh, set) and protocol.name in refresh)
        entry = None if wants_refresh else cache.get(protocol.name, text_hash, structure_hash)
        result = _validate(extractor, entry)
        if result is None:
            todo.append((protocol, text_hash))
            continue
        run.results[protocol.name] = result
        if entry.migrated:
            cache.put(protocol.name, entry, text_hash, structure_hash)   # ins neue Format umschreiben
        if entry.model != model_name or entry.prompt_hash != prompt_hash:
            outdated.append(f"{protocol.name} ({entry.model})")

    if outdated:
        log.info("%d Ergebnis(se) im Cache stammen von einem anderen Modell oder einem älteren Prompt. "
                 "Neu auswerten: tbd sync --refresh [PROTOKOLL …]", len(outdated))
        log.debug("  %s", ", ".join(outdated))

    if not todo:
        return run
    if llm is None:
        run.missing = [p.name for p, _ in todo]
        log.warning("%d Protokoll(e) noch nicht extrahiert – dafür 'tbd sync' ausführen.", len(todo))
        return run

    llm.check()
    log.info("Extrahiere %s aus %d Protokoll(en) mit %s …", extractor.name, len(todo), llm.model)
    for number, (protocol, text_hash) in enumerate(todo, start=1):
        started = time.monotonic()
        user = extractor.user_message(user_template, protocol, context)
        _warn_if_too_long(protocol.name, system + user, llm.num_ctx)
        result = _ask_with_retry(llm, extractor, system, user, schema)
        if result is None:
            run.missing.append(protocol.name)
            log.error("  [%d/%d] %s: fehlgeschlagen", number, len(todo), protocol.name)
            continue
        entry = CacheEntry(result=result.model_dump(mode="json"), model=llm.model, prompt_hash=prompt_hash)
        cache.put(protocol.name, entry, text_hash, structure_hash)
        run.results[protocol.name] = result
        extractor.learn(result, context)
        log.info("  [%d/%d] %s: %s (%.0f s)", number, len(todo), protocol.name,
                 _summary(result), time.monotonic() - started)
    return run


def _validate(extractor: Extractor, entry: CacheEntry | None) -> BaseModel | None:
    """Prüft, ob ein Cache-Eintrag noch zum Datenmodell passt (wichtig bei alten Einträgen)."""
    if entry is None:
        return None
    try:
        return extractor.result_model.model_validate(entry.result)
    except ValidationError:
        return None


def _warn_if_too_long(protocol_name: str, prompt: str, num_ctx: int) -> None:
    """Grobe Schätzung (deutscher Text: ca. 3 Zeichen pro Token).

    Ist der Prompt länger als num_ctx, schneidet Ollama ihn stillschweigend ab –
    dann fehlen dem Modell Teile der Anweisungen oder des Protokolls.
    """
    estimated = len(prompt) // 3
    if estimated > num_ctx * 0.75:
        log.warning("  %s: Prompt hat ca. %d Tokens, num_ctx ist %d – ggf. num_ctx in "
                    ".tbd/config.yaml erhöhen.", protocol_name, estimated, num_ctx)


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
