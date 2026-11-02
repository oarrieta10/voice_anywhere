"""Simple, predictable cleanup of the transcribed text before it is pasted. Fully offline.

Works for English and Spanish. Rules, in order:
  1. Filler sounds are removed, with the commas around them:
       English: um, uh, uhm, er, erm, hmm      Spanish: eh, em, mmm
     "I think, um, we should" -> "I think we should"
     "Creo que, eh, deberíamos" -> "Creo que deberíamos"
     Real words that are also used as fillers ("este", "o sea", "like") are left alone,
     because removing them could change the meaning.
  2. A word said twice in a row is kept once: "the the report" -> "the report".
     Words that are often doubled on purpose are left alone ("that that", "had had",
     "no no", "sí sí", "ya ya", ...).
  3. Spacing and punctuation are tidied: no double spaces, no space before a comma or
     full stop, no ",." left behind.
  4. Where a filler was removed from the start of a sentence, the next word gets its
     capital back ("Um, so we..." -> "So we...", "Eh, ¿qué tal?" -> "¿Qué tal?").
Settings:
  VOICE_CLEANUP  "on" (default) or "off"
"""
import os
import re

FILLERS = r"(?:u+m+|u+h+|uhm|e+r+m*|h+m+|e+h+|e+m+|m{2,})"
_MARK = "\x00"  # marks where a filler was taken out, for rule 4
# A filler as a whole word (not part of "uh-huh" or "'em"), with an optional comma before
# and after.
_FILLER = re.compile(r"(?:,\s*|\s+|^)(?<![-'’])\b" + FILLERS + r"\b(?![-'’])(?:\s*,)?",
                     re.IGNORECASE)
KEEP_DOUBLED = {"that", "had", "is", "no", "so", "very", "bye", "ha", "hey", "now", "well",
                "sí", "si", "ya", "muy", "adiós", "ay", "ja", "poco", "casi"}
_WORD = r"[^\W\d_]+(?:['’][^\W\d_]+)?"  # letters in any language, with "it's"-style apostrophes
_DOUBLED = re.compile(r"\b(" + _WORD + r")(?:[\s,]+\1\b)+", re.IGNORECASE)
# A marked spot at the start of the text or of a sentence, then (after any spaces, commas
# and an opening ¿ or ¡) the first letter of the next word.
_MARKED_START = re.compile(r"(^|[.!?])(\s*)" + _MARK + r"[\s,]*([¿¡]?)([^\W\d_])")


def enabled() -> bool:
    return os.environ.get("VOICE_CLEANUP", "on").strip().lower() not in ("off", "0", "no", "false")


def _remove_fillers(text: str) -> str:
    # Keep a space between the words on either side; _tidy() removes any extra ones.
    return _FILLER.sub(lambda m: _MARK if m.start() == 0 else " " + _MARK, text)


def _restore_capitals(text: str, at_start: bool) -> str:
    def replace(match):
        start, space, opener, letter = match.groups()
        if start or at_start:
            letter = letter.upper()
        return start + space + opener + letter
    return _MARKED_START.sub(replace, text).replace(_MARK, "")


def _remove_doubles(text: str) -> str:
    def replace(match):
        word = match.group(1)
        return match.group(0) if word.lower() in KEEP_DOUBLED else word
    return _DOUBLED.sub(replace, text)


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # no space before punctuation
    text = re.sub(r",+([.;:!?])", r"\1", text)  # ",." -> "."
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"^[\s,.;:]+", "", text)  # nothing left dangling at the start
    return text.strip()


def clean(text: str) -> str:
    if not text:
        return text
    was_capitalised = text.lstrip()[:1].isupper() or text.lstrip()[1:2].isupper()
    cleaned = _restore_capitals(_remove_fillers(text), was_capitalised)
    cleaned = _tidy(_remove_doubles(cleaned))
    if not re.search(r"[^\W_]", cleaned):
        return ""  # nothing but fillers and punctuation
    return cleaned
