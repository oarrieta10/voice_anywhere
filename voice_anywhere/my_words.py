"""Oscar's own word list: names to expect, and fixes for words Whisper keeps getting wrong.

The list is a plain text file, %LOCALAPPDATA%\\voice-anywhere\\my-words.txt, opened from the
tray's "My words..." item. It is read again for each dictation, so a change counts from the
next one, with no restart. Fully offline. The log records how many words and fixes there are,
never which ones.

    # a note
    Kuadrant                a word to expect: given to Whisper as a hint (see transcriber.py)
    cool ant -> Kuadrant    a fix: what Whisper writes -> what to type instead

Fixes match whole words in any capitals ("ant" never changes "plant"), and a fix at the start
of a sentence keeps the capital letter. They apply even with VOICE_CLEANUP off.
"""
import logging
import os
import re

from . import settings

log = logging.getLogger("voice_anywhere")

MAX_WORDS = 50  # a long hint list can make Whisper write those words where they were not said
ARROWS = ("->", "→")
STARTER = """\
# My words for Voice Anywhere. Save this file and the change counts from the next dictation.
# Lines starting with # are notes and are ignored.
#
# Words to expect: one per line, such as names, places or technical terms. Whisper is more
# likely to pick them. Keep the list short (up to 50 are used).
#   Kuadrant
#
# Fixes: what Whisper writes -> what you want typed. Whole words only, any capitals.
#   cool ant -> Kuadrant

"""
_last_counts = None


def path():
    return settings.data_dir() / "my-words.txt"


def parse(text: str) -> tuple[list[str], dict[str, str]]:
    """The words to expect and the fixes ({what Whisper writes, in lower case: what to type})."""
    words, fixes = [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        arrow = next((a for a in ARROWS if a in line), None)
        if arrow is None:
            words.append(line)
            continue
        wrong, right = (part.strip() for part in line.split(arrow, 1))
        if wrong and right:  # a fix with one side missing is ignored
            fixes[" ".join(wrong.lower().split())] = right
    return words, fixes


def load() -> tuple[list[str], dict[str, str]]:
    """The list as saved now; empty if there is no file or it cannot be read."""
    global _last_counts
    try:
        words, fixes = parse(path().read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return [], {}
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("Could not read my-words.txt: %s", type(exc).__name__)
        return [], {}
    if (len(words), len(fixes)) != _last_counts:
        _last_counts = (len(words), len(fixes))
        log.info("My words: %d words to expect, %d fixes", len(words), len(fixes))
    return words, fixes


def hints() -> str | None:
    """The words to expect, as one line for Whisper, or None if there are none."""
    words = load()[0][:MAX_WORDS]
    return ", ".join(words) if words else None


def apply_fixes(text: str, fixes: dict[str, str]) -> str:
    if not text or not fixes:
        return text
    # Longest first, so "cool ant pump" wins over "cool ant". Spaces may vary.
    phrases = sorted(fixes, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(r"\s+".join(map(re.escape, p.split()))
                                                    for p in phrases) + r")(?!\w)",
                         re.IGNORECASE)

    def replace(match):
        right = fixes[" ".join(match.group(0).lower().split())]
        at_sentence_start = re.search(r"(^|[.!?]\s+)[¿¡]?$", text[:match.start()])
        styled = any(c.isupper() for c in right.split()[0][1:])  # "iPhone" stays as written
        if at_sentence_start and match.group(0)[0].isupper() and not styled:
            right = right[0].upper() + right[1:]
        return right
    return pattern.sub(replace, text)


def fix(text: str) -> str:
    """Apply the saved fixes to dictated text."""
    return apply_fixes(text, load()[1])


def open_in_editor(opener=os.startfile) -> None:
    """Open the list (in Notepad, or whatever opens .txt files), creating it the first time."""
    file = path()
    if not file.exists():
        file.write_text(STARTER, encoding="utf-8")
    opener(str(file))
