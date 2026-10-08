"""Stammdaten: Personen und Themen.

Die Stammdaten SIND die Notizen in den Ordnern Personen/ und Themen/ –
inklusive ihrer ``aliases``. Dieses Modul
  - löst Namen aus den Protokollen auf ([[Michelle]] für "Mitch"),
  - meldet Unbekanntes im Prüfbericht,
  - setzt die Entscheidungen aus dem Prüfbericht um.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from ..core.managed import RunDecisions
from ..core.names import NameIndex, as_link, normalize_name
from ..core.review import Decision, Option, Review, ReviewItem
from ..core.state import IgnoreList
from ..core.vault import Vault

log = logging.getLogger(__name__)

PERSON = "person"
TOPIC = "topic"
_FOLDER = {PERSON: "persons", TOPIC: "topics"}
_LABEL = {PERSON: "Person", TOPIC: "Thema"}


@dataclass
class Resolver:
    """Löst Personen- und Themennamen auf und sammelt Unbekanntes."""

    persons: NameIndex
    topics: NameIndex
    ignore_names: set[str]          # normalisierte Namen aus der Konfiguration
    ignored: IgnoreList
    review: Review
    unknown: dict[str, set[str]] = field(default_factory=lambda: {PERSON: set(), TOPIC: set()})

    @classmethod
    def from_vault(cls, vault: Vault, ignored: IgnoreList, review: Review) -> "Resolver":
        return cls(
            persons=vault.name_index("persons"),
            topics=vault.name_index("topics"),
            ignore_names={normalize_name(n) for n in vault.config.ignore_names},
            ignored=ignored,
            review=review,
        )

    def person(self, raw: str, protocol: str) -> str | None:
        """'[[Michelle]]' für bekannte Namen, den Rohtext für unbekannte, None für Ignoriertes."""
        if not raw.strip() or normalize_name(raw) in self.ignore_names:
            return None
        return self._resolve(PERSON, self.persons, raw.strip(), protocol)

    def topic(self, raw: str, subtopic: str, protocol: str) -> tuple[str | None, str]:
        """Gibt (Wert für die Property 'thema', stabiler Themenschlüssel) zurück.

        Unterthemen heißen "Thema - Unterthema". Ist ein Unterthema (noch) unbekannt,
        wird ersatzweise das Hauptthema verlinkt.
        """
        raw = raw.strip()
        if not raw:
            return None, ""
        main = self._resolve(TOPIC, self.topics, raw, protocol)
        main_name = self.topics.resolve(raw) or raw
        key = normalize_name(main_name)
        if main is None:
            return None, key
        if subtopic.strip():
            sub = self._resolve(TOPIC, self.topics, f"{main_name} - {subtopic.strip()}", protocol)
            if sub and sub.startswith("[["):
                return sub, key
        return main, key

    def _resolve(self, kind: str, index: NameIndex, raw: str, protocol: str) -> str | None:
        known = index.resolve(raw)
        if known:
            return as_link(known)
        item_id = f"{kind}:{normalize_name(raw)}"
        if item_id in self.ignored:
            return None
        self.unknown[kind].add(raw)
        suggestion = index.suggest(raw)
        self.review.add(ReviewItem(
            id=item_id,
            title=raw,
            options=[
                Option("create", f"Neu anlegen ({_LABEL[kind]})"),
                Option("alias", f"Alias von [[{suggestion or ''}]]"),
                Option("ignore", f"Ignorieren – ist kein(e) {_LABEL[kind]}"),
            ],
        ), occurrence=protocol)
        return raw   # unbekannt: Rohtext bleibt sichtbar, bis es geklärt ist


def create_unknown(vault: Vault, resolver: Resolver) -> int:
    """Legt für alle unbekannten Namen Notizen an (nur im --initial-Modus)."""
    created = 0
    for name in sorted(resolver.unknown[PERSON]):
        created += vault.create_person(name) is not None
    # Hauptthemen vor Unterthemen anlegen
    for name in sorted(resolver.unknown[TOPIC], key=lambda n: (" - " in n, n)):
        created += vault.create_topic(name) is not None
    return created


def apply_decisions(vault: Vault, decisions: list[Decision], ignored: IgnoreList) -> RunDecisions:
    """Setzt angehakte Optionen aus dem Prüfbericht um."""
    result = RunDecisions()
    by_item: dict[str, list[Decision]] = defaultdict(list)
    for decision in decisions:
        by_item[decision.item_id].append(decision)

    for item_id, item_decisions in by_item.items():
        title = item_decisions[0].title
        if len(item_decisions) > 1:
            result.done.append(f"⚠️ „{title}“: mehrere Optionen angehakt – nichts geändert")
            continue
        decision = item_decisions[0]
        message = _apply_one(vault, decision, ignored, result)
        if message:
            result.done.append(message)
            log.info("Prüfbericht: %s", message)
    return result


def _apply_one(vault: Vault, d: Decision, ignored: IgnoreList, result: RunDecisions) -> str | None:
    if d.action == "ignore":
        ignored.add(d.item_id)
        return f"Ignoriert: {d.title}"

    if d.kind in (PERSON, TOPIC):
        folder = _FOLDER[d.kind]
        if d.action == "create":
            created = vault.create_person(d.title) if d.kind == PERSON else vault.create_topic(d.title)
            return f"{_LABEL[d.kind]} angelegt: [[{d.title}]]" if created else f"Existiert bereits: [[{d.title}]]"
        if d.action == "alias":
            if not d.target:
                return f"⚠️ „{d.title}“: kein Name im Alias-Link eingetragen"
            if vault.add_alias(folder, d.target, d.title):
                return f"„{d.title}“ als Alias von [[{d.target}]] eingetragen"
            return f"⚠️ „{d.title}“: [[{d.target}]] gibt es nicht im Ordner {vault.config.folders[folder]}"

    if d.kind == "conflict" and d.action == "accept":
        result.accepted_conflicts.add(d.item_id)
        return None      # Meldung kommt beim Schreiben, wenn der Wert wirklich übernommen wurde
    if d.kind == "orphan" and d.action == "delete":
        result.deletions.add(d.item_id)
        return None
    if d.kind == "duplicate" and d.action == "merge":
        result.merges.add(d.item_id)
        return None      # Meldung kommt beim Zusammenführen

    return f"⚠️ Unbekannte Aktion „{d.action}“ bei „{d.title}“"
