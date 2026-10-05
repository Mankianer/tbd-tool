from pathlib import Path

from tbd.core.managed import ManagedWriter, RunDecisions
from tbd.core.notes import Note
from tbd.core.review import Review
from tbd.core.state import IgnoreList, State


def make_writer(tmp_path: Path, decisions=None):
    review = Review()
    writer = ManagedWriter(tmp_path, State(tmp_path / "state.json"), review,
                           IgnoreList(tmp_path / "ignored.yaml"), decisions or RunDecisions())
    return writer, review


def test_tool_updates_its_own_values(tmp_path):
    writer, review = make_writer(tmp_path)
    note = Note(tmp_path / "n.md")
    writer.write(note, "x", {"ort": "Pfarrgarten"})
    writer.write(note, "x", {"ort": "Gemeindezentrum"})
    assert note.props["ort"] == "Gemeindezentrum"
    assert not review.items


def test_manual_change_is_kept_and_reported(tmp_path):
    writer, review = make_writer(tmp_path)
    note = Note(tmp_path / "n.md")
    writer.write(note, "x", {"uhrzeit": "17:00"})
    note.props["uhrzeit"] = "16:30"                       # Mensch ändert
    writer.write(note, "x", {"uhrzeit": "17:00"})          # gleicher Protokollwert -> kein Konflikt
    assert note.props["uhrzeit"] == "16:30" and not review.items
    writer.write(note, "x", {"uhrzeit": "18:00"})          # Protokoll sagt etwas Neues -> Konflikt
    assert note.props["uhrzeit"] == "16:30"
    assert len(review.items) == 1


def test_accepted_conflict_overwrites(tmp_path):
    writer, review = make_writer(tmp_path)
    note = Note(tmp_path / "n.md")
    writer.write(note, "x", {"uhrzeit": "17:00"})
    note.props["uhrzeit"] = "16:30"
    writer.write(note, "x", {"uhrzeit": "18:00"})
    [conflict_id] = review.items
    writer.decisions.accepted_conflicts.add(conflict_id)
    writer.write(note, "x", {"uhrzeit": "18:00"})
    assert note.props["uhrzeit"] == "18:00"


def test_empty_protocol_value_never_erases(tmp_path):
    writer, _ = make_writer(tmp_path)
    note = Note(tmp_path / "n.md")
    writer.write(note, "x", {"ort": "HMH"})
    writer.write(note, "x", {"ort": None})
    assert note.props["ort"] == "HMH"
