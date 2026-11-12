"""
Spendhound verifier: the AI may explain numbers, never invent them (rule #1 in CLAUDE.md).

Every number in an AI response is extracted and matched against the facts the AI was given.
One unknown number blocks the whole response. This is deliberately strict: when it blocks too
often, tighten the prompt, not this file.

What counts as a number:
  - digits in any form: 12, 1,234, 3.5, ₪1,234, 12%, 4.2x, 1.2k, 3M
  - ISO dates (2026-10-28), checked as whole dates
  - number words two..twenty, dozen, hundred, thousand, million, billion
    ("one" is skipped: it is usually a pronoun, as in "this one")
Signs are ignored: "-35%" and "35%" are the same claim about size.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

# Matching tolerance. Covers display rounding of a value we computed (₪12,345.67 shown as
# ₪12,346, CTR 0.023148 shown as 2.31%), but not the model rounding on its own: ₪12k for
# ₪12,345 is 2.8% off and gets blocked.
REL_TOLERANCE = 0.005
ABS_TOLERANCE = 1e-9            # only so that 0 matches 0

SUFFIX_MULTIPLIER = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}

NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "dozen": 12, "hundred": 100, "thousand": 1e3, "million": 1e6, "billion": 1e9,
}

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMBER = re.compile(
    r"(?<![\d.])"                          # not the tail of a longer number
    r"(\d{1,3}(?:,\d{3})+|\d+)"            # integer part, with or without thousands commas
    r"(?:\.(\d+))?"                        # decimals
    r"(?:(\s?%)|([kKmM])(?![a-zA-Z])|[x×](?![a-zA-Z]))?"
)
_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


@dataclass(frozen=True)
class Token:
    raw: str                    # as written in the text
    candidates: tuple           # values it may stand for (12% -> 12 and 0.12)


@dataclass
class Verification:
    ok: bool
    unknown: list = field(default_factory=list)      # raw strings of numbers not in the facts
    checked: int = 0                                 # how many numbers were found and checked

    def to_dict(self):
        return {"ok": self.ok, "unknown": list(self.unknown), "checked": self.checked}


def extract(text):
    """All numeric claims in `text`: (number tokens, ISO date strings)."""
    dates = [m.group(0) for m in _ISO_DATE.finditer(text)]
    rest = _ISO_DATE.sub(" ", text)
    tokens = []
    for m in _NUMBER.finditer(rest):
        whole, decimals, percent, suffix = m.groups()
        value = float(whole.replace(",", "") + ("." + decimals if decimals else ""))
        if percent:
            candidates = (value, value / 100)
        elif suffix:
            candidates = (value * SUFFIX_MULTIPLIER[suffix],)
        else:
            candidates = (value,)
        tokens.append(Token(m.group(0).strip(), candidates))
    for m in _WORD.finditer(rest):
        tokens.append(Token(m.group(0), (float(NUMBER_WORDS[m.group(1).lower()]),)))
    return tokens, dates


def allowed_values(facts):
    """Numbers and dates the AI may quote: every value in `facts`, plus every number written
    inside a text fact (evidence sentence, campaign name, a pre-formatted "₪12,346")."""
    numbers, dates = set(), set()

    def add(value):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (datetime, date)) or hasattr(value, "strftime"):
            dates.add(f"{value:%Y-%m-%d}")
        elif isinstance(value, (int, float)) or hasattr(value, "__float__"):
            v = float(value)
            if math.isfinite(v):
                numbers.add(abs(v))
        elif isinstance(value, str):
            tokens, found_dates = extract(value)
            dates.update(found_dates)
            for t in tokens:
                numbers.update(abs(c) for c in t.candidates)
        elif isinstance(value, dict):
            for k, v in value.items():
                add(k)          # labels carry numbers too: "Spend, last 14 days"
                add(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                add(v)

    add(facts)
    return numbers, dates


def _matches(candidate, allowed):
    c = abs(candidate)
    return any(abs(c - a) <= max(REL_TOLERANCE * a, ABS_TOLERANCE) for a in allowed)


def _texts(output):
    """Every string inside an AI output (str, or JSON-like dict/list)."""
    if isinstance(output, str):
        yield output
    elif isinstance(output, dict):
        for v in output.values():
            yield from _texts(v)
    elif isinstance(output, (list, tuple)):
        for v in output:
            yield from _texts(v)


def verify(output, facts):
    """Checks every number in `output` (a string or the parsed JSON) against `facts`."""
    numbers, dates = allowed_values(facts)
    unknown, checked = [], 0
    for text in _texts(output):
        tokens, found_dates = extract(text)
        checked += len(tokens) + len(found_dates)
        unknown += [d for d in found_dates if d not in dates]
        unknown += [t.raw for t in tokens if not any(_matches(c, numbers) for c in t.candidates)]
    return Verification(ok=not unknown, unknown=list(dict.fromkeys(unknown)), checked=checked)
