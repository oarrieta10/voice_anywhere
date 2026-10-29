"""Simple, predictable cleanup of the transcribed text before it is pasted. Fully offline.

Rules, in order:
  1. Filler sounds are removed: um, uh, uhm, er, erm, hmm (with the commas around them).
     "I think, um, we should" -> "I think we should"
  2. A word said twice in a row is kept once: "the the report" -> "the report".
     Words that are often doubled on purpose are left alone ("that that", "had had",
     "no no", "bye bye", ...).
  3. Spacing and punctuation are tidied: no double spaces, no space before a comma or
     full stop, no ",." left behind.
  4. A sentence that now starts with a lower-case letter (because a filler was removed
     from its start) gets its capital back.
Settings:
  VOICE_CLEANUP  "on" (default) or "off"
"""
import os
import re

FILLERS = r"(?:u+m+|u+h+|uhm|e+r+m*|h+m+)"
# Filler, with an optional comma before and after. A filler at the very start keeps no space.
_FILLER = re.compile(r"(?:,\s*|\s+|^)" + r"\b" + FILLERS + r"\b(?:\s*,)?", re.IGNORECASE)
KEEP_DOUBLED = {"that", "had", "is", "no", "so", "very", "bye", "ha", "hey", "now", "well"}
_DOUBLED = re.compile(r"\b([A-Za-z']+)(?:[\s,]+\1\b)+", re.IGNORECASE)
_SENTENCE_START = re.compile(r"(^|[.!?]\s+)([a-z])")


def enabled() -> bool:
    return os.environ.get("VOICE_CLEANUP", "on").strip().lower() not in ("off", "0", "no", "false")


def _remove_fillers(text: str) -> str:
    # Keep a space between the words on either side; _tidy() removes any extra ones.
    return _FILLER.sub(lambda m: "" if m.start() == 0 else " ", text)


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
    was_capitalised = text.lstrip()[:1].isupper()
    cleaned = _tidy(_remove_doubles(_remove_fillers(text)))
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return ""  # nothing but fillers and punctuation
    if was_capitalised:
        cleaned = _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), cleaned)
    return cleaned
