from datetime import date

from tbd.core.extraction import ExtractionContext, ProtocolText
from tbd.features.appointments.extractor import AppointmentExtractor


def test_user_message_contains_everything_variable():
    extractor = AppointmentExtractor()
    system, template = extractor.load_prompts()
    protocol = ProtocolText("2026-09-18", date(2026, 9, 18), "* Vortreffen 25.09.")
    context = ExtractionContext(known_topics=["Ponyfreizeit"], known_persons=["Michelle (Mitch)"])

    user = extractor.user_message(template, protocol, context)

    assert "{{" not in system and "{{" not in user
    assert "Freitag, 18.09.2026" in user
    assert "- Ponyfreizeit" in user and "- Michelle (Mitch)" in user
    assert user.rstrip().endswith("* Vortreffen 25.09.")
