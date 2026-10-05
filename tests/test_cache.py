"""Verhalten des Extraktions-Caches."""

import json
from datetime import date

from tbd.core.extraction import ExtractionCache, ExtractionContext, ProtocolText, run_extractor
from tbd.features.appointments.extractor import AppointmentExtractor

from .fake_llm import FakeLLM

PROTOCOLS = [
    ProtocolText("2026-09-11", date(2026, 9, 11), "* Martinsumzug 13.11."),
    ProtocolText("2026-09-18", date(2026, 9, 18), "* Vortreffen Ponyfreizeit 25.09."),
]


def extract(tmp_path, llm, protocols=PROTOCOLS, model_name="modell-a", refresh=False, extractor=None):
    extractor = extractor or AppointmentExtractor()
    cache = ExtractionCache(tmp_path, extractor.name)
    return run_extractor(extractor, protocols, cache, model_name, ExtractionContext(), llm, refresh)


def test_other_model_reuses_cache(tmp_path):
    llm = FakeLLM()
    extract(tmp_path, llm, model_name="modell-a")
    assert llm.calls == 2
    run = extract(tmp_path, llm, model_name="modell-b")
    assert llm.calls == 2 and run.complete


def test_changed_prompt_reuses_cache(tmp_path):
    llm = FakeLLM()
    extract(tmp_path, llm)
    extractor = AppointmentExtractor()
    extractor.load_prompts = lambda: ("ganz neuer Prompt", "{{protocol_text}}")
    extract(tmp_path, llm, extractor=extractor)
    assert llm.calls == 2


def test_changed_protocol_text_is_extracted_again(tmp_path):
    llm = FakeLLM()
    extract(tmp_path, llm)
    changed = [PROTOCOLS[0], ProtocolText("2026-09-18", date(2026, 9, 18), "* Vortreffen 26.09.")]
    extract(tmp_path, llm, protocols=changed)
    assert llm.calls == 3


def test_changed_structure_is_extracted_again(tmp_path):
    llm = FakeLLM()
    extract(tmp_path, llm)
    extractor = AppointmentExtractor()
    extractor.version = 99
    extract(tmp_path, llm, extractor=extractor)
    assert llm.calls == 4


def test_refresh_all_or_selected(tmp_path):
    llm = FakeLLM()
    extract(tmp_path, llm)
    extract(tmp_path, llm, refresh={"2026-09-18"})
    assert llm.calls == 3
    extract(tmp_path, llm, refresh=True)
    assert llm.calls == 5


def test_cache_records_model(tmp_path):
    llm = FakeLLM()
    extract(tmp_path, llm)
    data = json.loads((tmp_path / "cache" / "appointments" / "2026-09-11.json").read_text())
    assert data["model"] == "fake" and data["format"] == 2


def test_old_cache_format_is_migrated(tmp_path):
    folder = tmp_path / "cache" / "appointments"
    folder.mkdir(parents=True)
    old = {"appointments": [{"title": "Martinsumzug", "kind": "veranstaltung", "date_text": "13.11."}]}
    for p in PROTOCOLS:
        (folder / f"{p.name}.json").write_text(json.dumps({"key": "alter-schluessel", "result": old}))

    llm = FakeLLM()
    run = extract(tmp_path, llm)
    assert llm.calls == 0
    assert run.results["2026-09-11"].appointments[0].title == "Martinsumzug"
    data = json.loads((folder / "2026-09-11.json").read_text())
    assert data["format"] == 2 and data["model"] == "unbekannt"

    # Nach der Übernahme wird der Protokolltext wieder geprüft
    changed = [ProtocolText("2026-09-11", date(2026, 9, 11), "* Martinsumzug 14.11."), PROTOCOLS[1]]
    extract(tmp_path, llm, protocols=changed)
    assert llm.calls == 1


def test_broken_old_entry_is_extracted_again(tmp_path):
    folder = tmp_path / "cache" / "appointments"
    folder.mkdir(parents=True)
    (folder / "2026-09-11.json").write_text(json.dumps({"key": "x", "result": {"appointments": "kaputt"}}))
    llm = FakeLLM()
    extract(tmp_path, llm, protocols=PROTOCOLS[:1])
    assert llm.calls == 1
