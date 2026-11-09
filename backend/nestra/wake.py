"""The "Hi Nestra" wake phrase.

Hands-free mode sends every burst of speech the browser hears; only the ones
that start with the wake phrase are acted on. Whisper doesn't always spell
"Nestra" the same way ("Nestor", "Nastra", "Hinestra"...), so matching is fuzzy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

NAME = "nestra"
GREETINGS = {"hi", "hey", "hello", "ok", "okay", "yo", "hay", "high", "hai", "a", "oh"}
# Common mishearings. Only accepted after a greeting ("hi nestor"), never on their own.
SOUNDALIKES = {"nestor", "nester", "nastra", "nestrah", "nestro", "nesta", "nexstra", "nextra", "extra", "nostra", "ministra"}
_WORD = re.compile(r"[a-z']+")


@dataclass(frozen=True)
class Wake:
    heard: bool
    command: str = ""  # whatever was said after the wake phrase


def _like_name(word: str, *, strict: bool) -> bool:
    if word == NAME:
        return True
    if not strict and word in SOUNDALIKES:
        return True
    return SequenceMatcher(None, word, NAME).ratio() >= (0.85 if strict else 0.75)


def split_wake(text: str) -> Wake:
    """Does `text` start with the wake phrase? Returns the command after it.

    >>> split_wake("Hi, Nestra. Turn on the fan.")
    Wake(heard=True, command='Turn on the fan.')
    """
    words = [(m.group(), m.start(), m.end()) for m in _WORD.finditer(text.lower())]
    greeted = False
    for i, (word, _, end) in enumerate(words[:4]):
        candidates = [(word, end)]
        if i + 1 < len(words):  # "ness tra", "nest ra"
            candidates.append((word + words[i + 1][0], words[i + 1][2]))
        for greeting in ("hey", "hai", "high", "hi"):  # "hinestra", "heynestra"
            if len(word) > len(greeting) + 3 and word.startswith(greeting):
                candidates.append((word[len(greeting):], end))
                greeted_inline = True
                break
        else:
            greeted_inline = False
        for candidate, cand_end in candidates:
            if _like_name(candidate, strict=not (greeted or greeted_inline)):
                return Wake(True, text[cand_end:].lstrip(" ,.!?;:-").strip())
        if word in GREETINGS:
            greeted = True
            continue
        break  # the wake phrase has to come first
    return Wake(False)
