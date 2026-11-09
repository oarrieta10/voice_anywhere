import pytest

from voice_anywhere import my_words
from voice_anywhere.my_words import apply_fixes, parse


def write(text):
    my_words.path().write_text(text, encoding="utf-8")


def test_parse_reads_words_fixes_and_skips_notes():
    words, fixes = parse("# a note\n\n  Kuadrant \nArrieta\ncool ant -> Kuadrant\n"
                         "Eye  Phone→iPhone\n-> nothing\nhalf ->\n")
    assert words == ["Kuadrant", "Arrieta"]
    assert fixes == {"cool ant": "Kuadrant", "eye phone": "iPhone"}


FIXES = {"cool ant": "Kuadrant", "eye phone": "iPhone", "cool ant pump": "Kuadrant pump P-1",
         "ant": "ANT", "tag": "tag"}


@pytest.mark.parametrize("before, after", [
    ("We met at cool ant today.", "We met at Kuadrant today."),
    ("Cool ant called. Send it to COOL  ANT.", "Kuadrant called. Send it to Kuadrant."),
    ("Check the cool ant pump.", "Check the Kuadrant pump P-1."),  # longest fix wins
    ("The plant and the ant.", "The plant and the ANT."),  # whole words only
    ("My eye phone rang. Eye phone again.", "My iPhone rang. iPhone again."),
    ("Mi tag. Tag again.", "Mi tag. Tag again."),
    ("Mid Sentence Eye Phone stays as written.", "Mid Sentence iPhone stays as written."),
    ("¿Cool ant llamó?", "¿Kuadrant llamó?"),
    ("Nothing to fix here.", "Nothing to fix here."),
])
def test_fixes(before, after):
    assert apply_fixes(before, FIXES) == after


def test_no_fixes_changes_nothing():
    assert apply_fixes("cool ant", {}) == "cool ant"
    assert apply_fixes("", FIXES) == ""


def test_missing_file_means_an_empty_list():
    assert my_words.load() == ([], {})
    assert my_words.hints() is None
    assert my_words.fix("cool ant") == "cool ant"


def test_saved_list_is_read_for_each_dictation():
    write("Kuadrant\ncool ant -> Kuadrant\n")
    assert my_words.fix("Call cool ant.") == "Call Kuadrant."
    write("Kuadrant\ncool ant -> Quadrant\n")
    assert my_words.fix("Call cool ant.") == "Call Quadrant."


def test_hints_join_the_words_and_stop_at_the_limit():
    write("Kuadrant\nArrieta\nx -> y\n")
    assert my_words.hints() == "Kuadrant, Arrieta"
    write("\n".join(f"word{n}" for n in range(my_words.MAX_WORDS + 10)))
    assert my_words.hints().count(",") == my_words.MAX_WORDS - 1


def test_notepad_byte_order_mark_is_ignored():
    my_words.path().write_text("Kuadrant\n", encoding="utf-8-sig")
    assert my_words.load()[0] == ["Kuadrant"]


def test_unreadable_file_means_an_empty_list():
    my_words.path().write_bytes(b"\xff\xfe\xfa bad")
    assert my_words.load() == ([], {})


def test_log_has_counts_but_never_the_words(caplog):
    write("Kuadrant\ncool ant -> Kuadrant\n")
    my_words._last_counts = None
    with caplog.at_level("INFO", logger="voice_anywhere"):
        my_words.fix("cool ant")
    assert "1 words to expect, 1 fixes" in caplog.text
    assert "Kuadrant" not in caplog.text and "cool" not in caplog.text


def test_opening_creates_the_starter_file_once():
    opened = []
    my_words.open_in_editor(opener=opened.append)
    assert opened == [str(my_words.path())]
    assert my_words.load() == ([], {})  # the starter only has notes
    write("Kuadrant\n")
    my_words.open_in_editor(opener=opened.append)
    assert my_words.load()[0] == ["Kuadrant"]  # not overwritten
