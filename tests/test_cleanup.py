import pytest

from voice_anywhere import cleanup
from voice_anywhere.cleanup import clean


@pytest.mark.parametrize("before, after", [
    # fillers
    ("I think, um, we should send it.", "I think we should send it."),
    ("Um, so the pump is running.", "So the pump is running."),
    ("Uh the report is ready.", "The report is ready."),
    ("Send the uh drawings to Maria.", "Send the drawings to Maria."),
    ("We need more time, um.", "We need more time."),
    ("Hmm, let me check. Um, yes it works.", "Let me check. Yes it works."),
    ("Ummm, okay.", "Okay."),
    # doubled words
    ("The the valve is closed.", "The valve is closed."),
    ("I I think it's fine.", "I think it's fine."),
    ("Check the, the flow rate.", "Check the flow rate."),
    # doubles said on purpose stay
    ("He said that that was wrong.", "He said that that was wrong."),
    ("No no, keep it.", "No no, keep it."),
    # tidy spacing and punctuation
    ("Hello  world .", "Hello world."),
    ("Done , thanks", "Done, thanks"),
    # leave ordinary text alone
    ("Please send the revised pump calculations by Friday.",
     "Please send the revised pump calculations by Friday."),
    ("The summary is umbrella-shaped, uh, erm.", "The summary is umbrella-shaped."),
    ("Her name is Erma.", "Her name is Erma."),
])
def test_clean(before, after):
    assert clean(before) == after


def test_only_fillers_leaves_nothing():
    assert clean("Um.") == ""
    assert clean("Uh, um...") == ""


def test_lower_case_start_is_kept():
    # Whisper chose lower case (rare); cleanup does not force a capital.
    assert clean("um, and then the pump") == "and then the pump"


def test_empty_text():
    assert clean("") == ""


def test_can_be_switched_off(monkeypatch):
    monkeypatch.delenv("VOICE_CLEANUP", raising=False)
    assert cleanup.enabled()
    monkeypatch.setenv("VOICE_CLEANUP", "off")
    assert not cleanup.enabled()
