from datetime import date
from pathlib import Path

from tbd.core.notes import AUTO_END, AUTO_START, Note


def test_roundtrip_keeps_types(tmp_path: Path):
    path = tmp_path / "a.md"
    path.write_text("---\ndatum: 2026-09-25\nuhrzeit: 17:00\nzustaendig:\n- '[[Pia]]'\n---\nText\n")
    note = Note.load(path)
    assert note.props["datum"] == date(2026, 9, 25)
    assert note.props["uhrzeit"] == "17:00"          # nicht 1020!
    assert note.props["zustaendig"] == ["[[Pia]]"]
    assert note.save() is False                      # nichts geändert -> nicht schreiben


def test_auto_block_only_touches_marked_area(tmp_path: Path):
    note = Note.parse(tmp_path / "b.md", f"Oben\n{AUTO_START}\nalt\n{AUTO_END}\nUnten\n")
    note.set_auto_block("neu")
    assert note.get_auto_block() == "neu"
    assert note.body.startswith("Oben") and note.body.endswith("Unten\n")


def test_missing_markers_change_nothing(tmp_path: Path):
    note = Note.parse(tmp_path / "c.md", "Nur Text")
    assert note.set_auto_block("x") is False
    assert note.body == "Nur Text"
