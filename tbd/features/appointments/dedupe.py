"""Doppelte Termine zusammenführen.

``builder.py`` fasst nur Erwähnungen zusammen, deren Schlüssel (Art|Datum|Thema)
exakt gleich ist. Das Modell ist aber nicht immer einheitlich: Dasselbe Vortreffen
heißt in einem Protokoll "treffen", im nächsten "veranstaltung", oder es landet
einmal ohne Thema. Dieses Modul vergleicht deshalb alle Termine am SELBEN TAG
paarweise und entscheidet (siehe ``compare``):

  SAME      -> automatisch zusammenführen
  MAYBE     -> Vorschlag im Prüfbericht ("Zusammenführen" / "Getrennt lassen")
  DIFFERENT -> nichts tun

Im Prüfbericht bestätigte Zusammenführungen werden in .tbd/merged.yaml gespeichert
und gelten ab dann dauerhaft.

Welche Notiz bleibt? Die erste (älteste) Erwähnung, deren Notiz noch im Vault
existiert. So bleiben Handeingaben erhalten, und wer eine Dublette schon von Hand
gelöscht hat, verliert den Termin nicht. Die übrigen Notizen werden beim Schreiben
"verwaist" und – sofern unverändert – automatisch gelöscht.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
from itertools import combinations

from ...core.managed import RunDecisions
from ...core.names import normalize_name
from ...core.review import Option, Review, ReviewItem
from ...core.state import IgnoreList, MergeList
from .builder import MEETING, Appointment

log = logging.getLogger(__name__)

SAME, MAYBE, DIFFERENT = "same", "maybe", "different"

# Ab wann zwei Titel als ähnlich gelten (0 = nichts gemeinsam, 1 = identisch)
TITLE_SIMILARITY = 0.8      # Zeichen-Ähnlichkeit der ganzen Titel
WORD_OVERLAP = 0.6          # Anteil gemeinsamer Wörter, gemessen am kürzeren Titel


def compare(a: Appointment, b: Appointment) -> str:
    """Die Regeln – hier anpassen, wenn zu viel oder zu wenig zusammengeführt wird."""
    if a.date != b.date or a.date is None:
        return DIFFERENT
    same_topic = bool(a.topic_key) and a.topic_key == b.topic_key
    one_without_topic = not a.topic_key or not b.topic_key
    similar = similar_titles(a.title, b.title)

    if same_topic and (a.kind == b.kind or similar):
        return SAME
    if one_without_topic and similar:
        return SAME
    if similar:
        return MAYBE         # ähnlicher Titel, aber verschiedene Themen
    if same_topic:
        return MAYBE         # gleiches Thema, aber andere Art und anderer Titel
    return DIFFERENT


def similar_titles(a: str, b: str) -> bool:
    """'Vortreffen' ~ 'Vortreffen Ponyfreizeit', 'Infoabend Ponys' ~ 'Infoabend Pony'."""
    text_a, text_b = normalize_name(a), normalize_name(b)
    if not text_a or not text_b:
        return False
    if SequenceMatcher(None, text_a, text_b).ratio() >= TITLE_SIMILARITY:
        return True
    words_a, words_b = _words(text_a), _words(text_b)
    if not words_a or not words_b:
        return False
    shorter = min(len(words_a), len(words_b))
    return len(words_a & words_b) / shorter >= WORD_OVERLAP


def merge_duplicates(
    appointments: list[Appointment],
    existing_ids: set[str],
    merges: MergeList,
    decisions: RunDecisions,
    review: Review,
    ignored: IgnoreList,
) -> list[Appointment]:
    """Gibt die Termine zurück, in denen Dubletten zusammengeführt sind."""
    groups = _UnionFind(len(appointments))

    by_date: dict = defaultdict(list)
    for index, appointment in enumerate(appointments):
        if appointment.date and appointment.kind != MEETING:
            by_date[appointment.date].append(index)

    for indices in by_date.values():
        for i, j in combinations(indices, 2):
            a, b = appointments[i], appointments[j]
            verdict = compare(a, b)
            if verdict == DIFFERENT:
                continue
            if verdict == SAME or merges.contains(a.key, b.key):
                groups.union(i, j)
                continue
            item_id = _item_id(a, b)
            if item_id in decisions.merges:
                merges.add(a.key, b.key)
                groups.union(i, j)
                review.done.append(f"Termine zusammengeführt: {a.title} / {b.title} ({a.date:%d.%m.%Y})")
            elif item_id not in ignored:
                review.add(_suggestion(item_id, a, b))

    result = [_combine([appointments[i] for i in members], existing_ids) for members in groups.groups()]
    merged = len(appointments) - len(result)
    if merged:
        log.info("Doppelte Termine zusammengeführt: %d", merged)
    return sorted(result, key=lambda a: (a.date or date.max, a.title))


def _combine(members: list[Appointment], existing_ids: set[str]) -> Appointment:
    """Fasst eine Gruppe zu einem Termin zusammen."""
    if len(members) == 1:
        return members[0]
    # Welche Notiz bleibt: älteste Erwähnung mit vorhandener Notiz, sonst älteste überhaupt
    by_first_mention = sorted(members, key=lambda m: min(x.protocol for x in m.mentions))
    keeper = next((m for m in by_first_mention if m.note_id in existing_ids), by_first_mention[0])
    # Spätere Erwähnungen haben Vorrang -> in der Reihenfolge der letzten Erwähnung zusammenführen
    ordered = sorted(members, key=lambda m: max(x.protocol for x in m.mentions))
    combined = Appointment(key=keeper.key, kind=ordered[0].kind, title=ordered[0].title,
                           status=ordered[0].status, date=keeper.date,   # gleiches Datum in der Gruppe
                           topic_key=keeper.topic_key)
    for member in ordered:
        combined.merge(member)
    combined.mentions = _sorted_unique_mentions(combined.mentions)
    return combined


def _suggestion(item_id: str, a: Appointment, b: Appointment) -> ReviewItem:
    def describe(x: Appointment) -> str:
        return f"„{x.title}“ ({x.kind}, Thema: {x.topic or '–'}, aus {', '.join(x.sources)})"
    return ReviewItem(
        id=item_id,
        title=f"{a.date:%d.%m.%Y}: {a.title} / {b.title}",
        details=[f"- {describe(a)}", f"- {describe(b)}",
                 "Gleiches Datum – ist das derselbe Termin? Sind die Themen eigentlich dasselbe, "
                 "besser einen Alias im Thema eintragen, dann wird automatisch zusammengeführt."],
        options=[Option("merge", "Zusammenführen"), Option("ignore", "Getrennt lassen")],
    )


def _item_id(a: Appointment, b: Appointment) -> str:
    first, second = sorted((a.note_id, b.note_id))
    return f"duplicate:{first}:{second}"


def _sorted_unique_mentions(mentions):
    seen, result = set(), []
    for mention in sorted(mentions, key=lambda m: m.protocol):
        marker = (mention.protocol, " ".join(mention.quote.split()))
        if marker not in seen:
            seen.add(marker)
            result.append(mention)
    return result


def _words(text: str) -> set[str]:
    return {w for w in text.split() if len(w) > 2}


class _UnionFind:
    """Merkt sich, welche Termine zusammengehören (auch über Ecken: A=B und B=C -> A=B=C)."""

    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        root_i, root_j = self.find(i), self.find(j)
        if root_i != root_j:
            self.parent[max(root_i, root_j)] = min(root_i, root_j)

    def groups(self) -> list[list[int]]:
        result: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            result[self.find(i)].append(i)
        return list(result.values())
