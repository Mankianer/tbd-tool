from datetime import date

from tbd.core.managed import RunDecisions
from tbd.core.review import Review
from tbd.core.state import IgnoreList, MergeList
from tbd.features.appointments.builder import Appointment, Mention
from tbd.features.appointments.dedupe import DIFFERENT, MAYBE, SAME, compare, merge_duplicates, similar_titles

DAY = date(2026, 9, 25)


def make(title, kind="treffen", topic="ponyfreizeit", day=DAY, protocol="2026-09-11", **extra):
    link = f"[[{topic.title()}]]" if topic else None
    return Appointment(key=f"{kind}|{day}|{topic}", kind=kind, title=title, status="geplant", date=day,
                       topic=link, topic_key=topic, mentions=[Mention(protocol, title)], **extra)


def run(appointments, tmp_path, existing=(), decisions=None, merges=None):
    review = Review()
    merges = merges or MergeList(tmp_path / "merged.yaml")
    result = merge_duplicates(appointments, set(existing), merges, decisions or RunDecisions(),
                              review, IgnoreList(tmp_path / "ignored.yaml"))
    return result, review, merges


def test_similar_titles():
    assert similar_titles("Vortreffen", "Vortreffen Ponyfreizeit")
    assert similar_titles("Infoabend Ponys", "Infoabend Pony")
    assert not similar_titles("Vortreffen Ponyfreizeit", "Brötchen bestellen")


def test_rules():
    assert compare(make("Vortreffen"), make("Vortreffen Ponyfreizeit", kind="veranstaltung")) == SAME
    assert compare(make("Vortreffen"), make("Vortreffen", topic="")) == SAME
    assert compare(make("Vortreffen"), make("Vortreffen", topic="pferdefreizeit")) == MAYBE
    assert compare(make("Abfahrt"), make("Anmeldeschluss", kind="deadline")) == MAYBE
    assert compare(make("Vortreffen"), make("Konzert", topic="chor")) == DIFFERENT
    assert compare(make("Vortreffen"), make("Vortreffen", day=date(2026, 9, 26))) == DIFFERENT


def test_merge_keeps_later_details_and_all_sources(tmp_path):
    early = make("Vortreffen", protocol="2026-09-11", time="17:00")
    late = make("Vortreffen Ponyfreizeit", kind="veranstaltung", protocol="2026-09-18",
                time="16:30", responsible=["[[Pia]]"])
    [merged], review, _ = run([early, late], tmp_path)
    assert merged.key == early.key                      # älteste Erwähnung bestimmt die Notiz
    assert merged.date == DAY
    assert (merged.title, merged.time, merged.kind) == ("Vortreffen Ponyfreizeit", "16:30", "veranstaltung")
    assert merged.responsible == ["[[Pia]]"]
    assert merged.sources == ["[[2026-09-11]]", "[[2026-09-18]]"]
    assert not review.items


def test_existing_note_is_kept(tmp_path):
    early, late = make("Vortreffen"), make("Vortreffen", kind="veranstaltung", protocol="2026-09-18")
    [merged], _, _ = run([early, late], tmp_path, existing={late.note_id})
    assert merged.note_id == late.note_id               # die Notiz, die es noch gibt, bleibt


def test_maybe_goes_to_review_and_merge_decision_is_remembered(tmp_path):
    a, b = make("Vortreffen"), make("Vortreffen", topic="pferdefreizeit", protocol="2026-09-18")
    result, review, _ = run([a, b], tmp_path)
    assert len(result) == 2
    [item_id] = review.items

    decisions = RunDecisions(merges={item_id})
    result, review, merges = run([a, b], tmp_path, decisions=decisions)
    assert len(result) == 1 and "zusammengeführt" in review.done[0]

    # Beim nächsten Lauf reicht die gespeicherte Entscheidung
    merges.save()
    result, review, _ = run([a, b], tmp_path, merges=MergeList.load(tmp_path))
    assert len(result) == 1 and not review.items


def test_chain_is_merged(tmp_path):
    a = make("Vortreffen", protocol="2026-09-04")
    b = make("Vortreffen Ponyfreizeit", kind="veranstaltung", protocol="2026-09-11")
    c = make("Vortreffen", topic="", protocol="2026-09-18")
    [merged], _, _ = run([a, b, c], tmp_path)
    assert len(merged.mentions) == 3
