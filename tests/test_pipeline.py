"""Ende-zu-Ende-Test mit simuliertem Modell (siehe fake_llm.py)."""

import re
from datetime import date
from pathlib import Path

import pytest

from tbd import pipeline
from tbd.config import load_config
from tbd.core.notes import Note

from .fake_llm import FakeLLM

EXPORT = """\
**Helferkreis Besprechungspunkte**

18\\.09.2026

* Ponyfreizeit 02.10.2026
  * Vortreffen Ponyfreizeit 25.09. 17 Uhr, Pia kümmert sich
  * Brötchen bestellen bis 20.09. (Mitch)
* Nächste Woche 25.09. kein TBD

11.09.2026

* Ponyfreizeit Vortreffen 25.09. 17 Uhr
* Martinsumzug 13.11. – Kira hilft
"""


@pytest.fixture
def vault(tmp_path, monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(pipeline.OllamaClient, "from_config", classmethod(lambda cls, cfg: fake))
    root = tmp_path / "vault"
    root.mkdir()
    (tmp_path / "export.md").write_text(EXPORT, encoding="utf-8")
    config = load_config(root)
    pipeline.init(config)
    return root, load_config(root), tmp_path / "export.md", fake


def sync(config, export=None, **kwargs):
    pipeline.run(config, pipeline.RunOptions(export=export, today=date(2026, 9, 19), **kwargs))


def tick(report: str, title: str, action: str, target: str | None = None) -> str:
    """Hakt im Prüfbericht beim Eintrag 'title' die Option 'action' an."""
    head, *sections = report.split("\n### ")
    for i, section in enumerate(sections):
        if section.split("\n", 1)[0] == title:
            lines = section.split("\n")
            for j, line in enumerate(lines):
                if f"action: {action} " in line:
                    line = line.replace("- [ ]", "- [x]")
                    if target is not None:
                        line = re.sub(r"\[\[[^\]]*\]\]", f"[[{target}]]", line)
                    lines[j] = line
            sections[i] = "\n".join(lines)
    return "\n### ".join([head, *sections])


def appointment(root: Path, title_part: str) -> Note:
    [path] = [p for p in (root / "Termine").glob("*.md") if title_part in p.name]
    return Note.load(path)


def test_initial_run_creates_everything(vault):
    root, config, export, fake = vault
    sync(config, export, initial=True)

    assert {p.name for p in (root / "Protokolle").glob("*.md")} >= {"2026-09-11.md", "2026-09-18.md"}
    assert (root / "Personen" / "Pia.md").exists()
    assert (root / "Themen" / "Ponyfreizeit.md").exists()

    # Vortreffen wird in zwei Protokollen erwähnt -> eine Notiz mit zwei Quellen
    vortreffen = appointment(root, "2026-09-25 Vortreffen")
    assert vortreffen.props["datum"] == date(2026, 9, 25)
    assert vortreffen.props["thema"] == "[[Ponyfreizeit]]"
    assert set(vortreffen.props["quellen"]) == {"[[2026-09-11]]", "[[2026-09-18]]"}

    # Angekündigte Besprechung: "kein TBD" -> abgesagt
    meeting = Note.load(root / "Protokolle" / "2026-09-25.md")
    assert meeting.props["status"] == "abgesagt"
    assert Note.load(root / "Protokolle" / "2026-09-18.md").props["status"] == "stattgefunden"

    # Prompt-Caching: Die System-Nachricht ist für alle Protokolle identisch
    assert len(fake.system_prompts) == 2
    assert len(set(fake.system_prompts)) == 1
    assert "{{" not in fake.system_prompts[0]

    # Zweiter Lauf: alles aus dem Cache, keine LLM-Aufrufe
    calls = fake.calls
    sync(config, export)
    assert fake.calls == calls


def test_manual_edits_survive_and_review_decisions_apply(vault):
    root, config, export, _ = vault
    sync(config, export, initial=True)

    # Mensch korrigiert die Uhrzeit des Vortreffens
    note = appointment(root, "2026-09-25 Vortreffen")
    note.props["uhrzeit"] = "16:30"
    note.save()

    # "Mitch" und "Kira" sollen Aliase werden: Personen-Notizen löschen, Prüfbericht nutzen
    (root / "Personen" / "Mitch.md").unlink()
    (root / "Personen" / "Kira.md").unlink()
    (root / "Personen" / "Michelle.md").write_text("---\ntyp: person\n---\n", encoding="utf-8")
    (root / "Personen" / "Bellis.md").write_text("---\ntyp: person\n---\n", encoding="utf-8")
    pipeline.run(config, pipeline.RunOptions(use_llm=False, today=date(2026, 9, 19)))

    report = (root / "_System" / "Prüfbericht.md").read_text(encoding="utf-8")
    assert "### Mitch" in report and "### Kira" in report
    report = tick(report, "Mitch", "alias", "Michelle")
    report = tick(report, "Kira", "alias", "Bellis")
    (root / "_System" / "Prüfbericht.md").write_text(report, encoding="utf-8")

    pipeline.run(config, pipeline.RunOptions(use_llm=False, today=date(2026, 9, 19)))

    assert appointment(root, "2026-09-25 Vortreffen").props["uhrzeit"] == "16:30"
    assert "[[Michelle]]" in appointment(root, "Brötchen").props["zustaendig"]
    assert "[[Bellis]]" in appointment(root, "Martinsumzug").props["zustaendig"]
    assert "Mitch" in Note.load(root / "Personen" / "Michelle.md").props["aliases"]
    report = (root / "_System" / "Prüfbericht.md").read_text(encoding="utf-8")
    assert "### Mitch" not in report and "Zuletzt erledigt" in report


def test_deleted_appointment_is_not_recreated(vault):
    root, config, export, _ = vault
    sync(config, export, initial=True)
    path = appointment(root, "Martinsumzug").path
    path.unlink()
    sync(config, export)
    assert not path.exists()
    sync(config, export, restore_deleted=True)
    assert path.exists()


def test_lock_prevents_parallel_runs(vault):
    root, config, export, _ = vault
    (root / ".tbd" / "lock").write_text("{}")
    with pytest.raises(Exception, match="gesperrt"):
        sync(config, export)


def test_year_from_context_reaches_the_note(tmp_path, monkeypatch):
    """Protokoll 2025-05-23: 'Termine Pferdefreizeit (2026)' – das Jahr steht nur in der Überschrift."""

    class ContextLLM(FakeLLM):
        def chat_json(self, system, user, schema):
            self.calls += 1
            return {"appointments": [{
                "title": "Pferdefreizeit (Option)", "kind": "veranstaltung", "status": "vorschlag",
                "date_text": "08.05", "date": "2026-05-08", "date_end_text": "10.05", "date_end": "2026-05-10",
                "topic": "Ponyfreizeit", "quote": "08.05 - 10.05"}]}

    llm = ContextLLM()
    monkeypatch.setattr(pipeline.OllamaClient, "from_config", classmethod(lambda cls, cfg: llm))
    root = tmp_path / "vault"
    root.mkdir()
    export = tmp_path / "export.md"
    export.write_text("23.05.2025\n\n* Termine Pferdefreizeit (2026)\n  * 08.05 - 10.05\n", encoding="utf-8")
    config = load_config(root)
    pipeline.init(config)
    pipeline.run(config, pipeline.RunOptions(export=export, initial=True, today=date(2025, 5, 24)))

    note = appointment(root, "Pferdefreizeit")
    assert note.props["datum"] == date(2026, 5, 8)
    assert note.props["datum_bis"] == date(2026, 5, 10)
    report = (root / "_System" / "Prüfbericht.md").read_text(encoding="utf-8")
    assert report.count("aus dem Zusammenhang übernommen") == 1


def test_topic_overview_is_created(vault):
    root, config, export, _ = vault
    path = root / "Übersichten" / "Themenübersicht.md"
    note = Note.load(path)
    assert note.props["aktuell_zeitraum"] == "14 days"
    assert 'FROM "Termine"' in note.body and "{{" not in note.body

    # Eine von Hand angepasste Übersicht wird nicht überschrieben
    path.write_text("eigene Version", encoding="utf-8")
    sync(config, export, initial=True)
    assert path.read_text(encoding="utf-8") == "eigene Version"
