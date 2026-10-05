"""Der Ablauf eines Laufs – von oben nach unten lesbar.

    tbd sync   = Prüfbericht anwenden -> Export importieren -> extrahieren (LLM) -> schreiben
    tbd apply  = Prüfbericht anwenden ->                       nur Cache          -> schreiben

Neue Extraktoren (z.B. Aufgaben) werden in ``run`` als weiterer Block ergänzt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import Config, write_default_vault_config
from .core.extraction import ExtractionCache, ExtractionContext, run_extractor
from .core.llm import OllamaClient
from .core.lock import VaultLock
from .core.managed import ManagedWriter
from .core.review import Review, read_decisions
from .core.state import IgnoreList, State
from .core.vault import Vault
from .features import master_data
from .features.appointments.builder import build_appointments
from .features.appointments.extractor import AppointmentExtractor
from .features.appointments.writer import write_appointments
from .features.protocols.ingest import import_export, load_protocols
from .features.protocols.writer import write_meeting_notes

log = logging.getLogger(__name__)


@dataclass
class RunOptions:
    export: Path | None = None      # Google-Docs-Export, der importiert werden soll
    use_llm: bool = True            # False = nur Cache (tbd apply)
    initial: bool = False           # unbekannte Personen/Themen direkt als Notizen anlegen
    refresh: bool = False           # Cache ignorieren, alles neu extrahieren
    restore_deleted: bool = False   # gelöschte Terminnotizen wieder anlegen
    force: bool = False             # Sperrdatei ignorieren
    today: date | None = None       # für Tests


def init(config: Config) -> None:
    vault = Vault(config)
    if write_default_vault_config(config.vault):
        log.info("Konfiguration angelegt: %s", config.tool_dir / "config.yaml")
    vault.ensure_structure()
    log.info("Vault ist eingerichtet: %s", config.vault)


def run(config: Config, options: RunOptions) -> None:
    vault = Vault(config)
    vault.ensure_structure()
    today = options.today or date.today()

    with VaultLock(vault.tool_dir, force=options.force):
        state = State.load(vault.tool_dir)
        ignored = IgnoreList.load(vault.tool_dir)

        # 1. Entscheidungen aus dem Prüfbericht umsetzen (Personen/Themen anlegen, Aliase, …)
        decisions = master_data.apply_decisions(vault, read_decisions(vault.review_path), ignored)

        # 2. Neuen Google-Docs-Export übernehmen
        if options.export:
            changed = import_export(vault, options.export)
            log.info("Protokolle aktualisiert: %d", changed)
        protocols = load_protocols(vault)

        # 3. Termine extrahieren (aus dem Cache oder per LLM)
        extractor = AppointmentExtractor()
        llm = OllamaClient.from_config(config) if options.use_llm else None
        extraction = run_extractor(
            extractor, protocols,
            cache=ExtractionCache(vault.tool_dir, extractor.name),
            model_name=config.model,
            context=_context(vault),
            llm=llm,
            refresh=options.refresh,
        )

        # 4. Termine bauen: Namen/Themen auflösen, Erwähnungen zusammenführen
        review = Review(done=decisions.done)
        resolver = master_data.Resolver.from_vault(vault, ignored, review)
        built = build_appointments(protocols, extraction.results, resolver, review, ignored)

        if options.initial:
            created = master_data.create_unknown(vault, resolver)
            log.info("Erstlauf: %d Personen/Themen angelegt", created)
            review = Review(done=decisions.done)          # neu bauen, jetzt mit den neuen Notizen
            resolver = master_data.Resolver.from_vault(vault, ignored, review)
            built = build_appointments(protocols, extraction.results, resolver, review, ignored)

        # 5. Notizen schreiben
        writer = ManagedWriter(vault.root, state, review, ignored, decisions)
        meetings = write_meeting_notes(vault, protocols, built.meetings, writer, today)
        stats = write_appointments(
            vault, built.appointments, writer, state, review, ignored, decisions,
            # Verwaiste Termine nur aufräumen, wenn wirklich alle Protokolle ausgewertet sind
            handle_orphans=extraction.complete,
            restore_deleted=options.restore_deleted,
        )

        # 6. Prüfbericht und Gedächtnis speichern
        review.save(vault.review_path)
        state.save()
        ignored.save()

    log.info("Fertig: %d Termine (%s), %d Besprechungsnotizen aktualisiert, %d offene Punkte im Prüfbericht.",
             len(built.appointments), ", ".join(f"{v} {k}" for k, v in stats.items()),
             meetings, len(review.items))
    if extraction.missing:
        log.warning("Nicht ausgewertet: %s", ", ".join(extraction.missing))


def _context(vault: Vault) -> ExtractionContext:
    return ExtractionContext(
        known_topics=vault.name_index("topics").describe(),
        known_persons=vault.name_index("persons").describe(),
    )
