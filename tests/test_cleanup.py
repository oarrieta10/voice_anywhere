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
    ("Emma said uh-huh.", "Emma said uh-huh."),
    ("Let 'em know.", "Let 'em know."),
    ("Mmm, that works.", "That works."),
    # a capital is only restored where a filler was removed
    ("We meet at 3 p.m. today.", "We meet at 3 p.m. today."),
    ("See e.g. the drawing.", "See e.g. the drawing."),
    # Spanish fillers
    ("Creo que, eh, deberíamos enviarlo.", "Creo que deberíamos enviarlo."),
    ("Eh, la bomba está funcionando.", "La bomba está funcionando."),
    ("Mmm, no estoy seguro.", "No estoy seguro."),
    ("Necesitamos, em, más tiempo.", "Necesitamos más tiempo."),
    ("Listo. Eh, ¿qué sigue?", "Listo. ¿Qué sigue?"),
    ("Eh, él llamó ayer.", "Él llamó ayer."),
    # Spanish doubled words
    ("El el informe está listo.", "El informe está listo."),
    ("Revisa la, la presión.", "Revisa la presión."),
    ("Sí sí, claro.", "Sí sí, claro."),
    ("Ya ya, lo sé.", "Ya ya, lo sé."),
    # real Spanish words that are sometimes fillers stay
    ("Este proyecto, o sea, el nuevo.", "Este proyecto, o sea, el nuevo."),
    ("Pues mira, está bien.", "Pues mira, está bien."),
    ("¿Cómo estás?", "¿Cómo estás?"),
])
def test_clean(before, after):
    assert clean(before) == after


@pytest.mark.parametrize("before, after", [
    # the phrase in the middle of a sentence
    ("The budget is fine. Send it to Bob, scratch that, send it to Alice.",
     "The budget is fine. Send it to Alice."),
    ("La cuenta está bien. Envíalo a Juan, borra eso, envíalo a Ana.",
     "La cuenta está bien. Envíalo a Ana."),
    # Whisper ended the sentence just before the phrase
    ("Send it to Bob. Scratch that. Send it to Alice.", "Send it to Alice."),
    ("All good. Send it to Bob. Scratch that, send it to Alice.",
     "All good. Send it to Alice."),
    ("Envíalo a Juan. Borra eso: envíalo a Ana.", "Envíalo a Ana."),
    ("¿Lo envío a Juan? ¡Borra eso! Envíalo a Ana.", "Envíalo a Ana."),
    # any capitals, and with no pause it still works
    ("Send it to Bob SCRATCH THAT send it to Alice.", "Send it to Alice."),
    # the next word gets a capital, also after an opening ¿
    ("Listo. Llama a Juan, borra eso, ¿llamamos a Ana?", "Listo. ¿Llamamos a Ana?"),
    ("Order 2 pumps, scratch that, 3 pumps.", "3 pumps."),
    # several in one dictation, left to right
    ("Send it to Bob, scratch that, send it to Carl, scratch that, send it to Alice.",
     "Send it to Alice."),
    ("First point. Bob, scratch that, Alice. Second point. Carl. Scratch that, Dana.",
     "First point. Alice. Second point. Dana."),
    # with fillers around the phrase
    ("Send it to Bob, um, scratch that, uh, send it to Alice.", "Send it to Alice."),
    ("Um, send it to Bob. Eh, borra eso, send it to Alice.", "Send it to Alice."),
    ("Let me check. Um, yes, scratch that, no.", "Let me check. No."),
    # an abbreviation is not the end of a sentence
    ("We meet at 3 p.m. today, scratch that, tomorrow.", "Tomorrow."),
    # "correction" is an ordinary word, however it is punctuated
    ("We need a correction to the invoice.", "We need a correction to the invoice."),
    ("Send it to Bob, correction, send it to Alice.",
     "Send it to Bob, correction, send it to Alice."),
    ("Envíalo a Juan. Corrección: envíalo a Ana.", "Envíalo a Juan. Corrección: envíalo a Ana."),
    ("We scratched that surface.", "We scratched that surface."),
])
def test_spoken_corrections(before, after):
    assert clean(before) == after


@pytest.mark.parametrize("text", [
    "Send it to Bob. Scratch that.", "Scratch that.", "Um, scratch that,", "Borra eso.",
    "Envíalo a Juan, borra eso.",
])
def test_erasing_everything_leaves_nothing(text):
    assert clean(text) == ""


def test_corrections_are_not_applied_when_cleanup_is_off(monkeypatch):
    from voice_anywhere.app import _clean

    monkeypatch.setenv("VOICE_CLEANUP", "off")
    text = "Send it to Bob, scratch that, send it to Alice."
    assert _clean(text) == text


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
