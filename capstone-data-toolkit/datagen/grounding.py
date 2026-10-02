"""Is an eval case's expected answer actually in the corpus?

The model that writes eval cases used to see only the document titles. Asked
for "a specific number from one document", it invented one: a 350 C oven
setpoint, a 30% glycol concentration, a co-pay. None of it was in the
documents the corpus stage had written, so a system that answered correctly
from the corpus was marked wrong.

From v1.0.4 the eval stage reads the corpus and these helpers check the result.
The test is deliberately simple and conservative: the figures an expected
answer states should appear in the documents it cites.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

#: Categories whose expected answer must come from the corpus.
GROUNDED_CATEGORIES = ("factual", "multi_hop")

# A figure, with the unit or word on either side of it: "$2,600", "350 C",
# "2,000 running hours", "30%".
_FIGURE = re.compile(
    r"(?:([$₹€£]|rs\.?|inr|usd)\s*)?"
    r"(\d+(?:,\d{2,3})*(?:\.\d+)?)"
    r"\s*-?\s*([^\s\d,.;:()\[\]]{1,15})?"
    r"(?:\s+([^\s\d,.;:()\[\]]{1,15}))?",
    re.IGNORECASE,
)
_MARKUP = re.compile(r"\\[a-zA-Z]+\{?|[{}*_`|\\]")
_STOP = {"to", "and", "or", "the", "of", "a", "an", "in", "for", "is", "at", "on",
         "by", "with", "under", "from", "as", "be", "are", "than", "-", "–", "—"}
_SAME = {
    "percent": "%", "pct": "%", "°c": "c", "celsius": "c", "degree": "c",
    "hr": "hour", "hrs": "hour", "min": "minute", "mins": "minute",
    "rupee": "inr", "rs": "inr", "rs.": "inr", "₹": "inr",
    "dollar": "usd", "$": "usd", "business": "day", "working": "day",
    "calendar": "day", "running": "hour", "operating": "hour",
}


def _unit(word: str | None) -> str | None:
    if not word:
        return None
    w = word.lower().strip("-–—/+±<>=≥≤~'\"")
    if len(w) > 3 and w.endswith("s"):
        w = w[:-1]
    w = _SAME.get(w, w)
    return None if not w or w in _STOP else w


def figures(text: str) -> dict[str, set[str]]:
    """{normalised number: units and words seen next to it}.

    '2,000' and '2000.0' both become '2000'. A lone digit is ignored: it
    proves nothing.
    """
    out: dict[str, set[str]] = {}
    for before, raw, after1, after2 in _FIGURE.findall(_MARKUP.sub(" ", text)):
        value = raw.replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        if len(value) < 2 and "." not in value:
            continue
        units = {u for u in (_unit(before), _unit(after1), _unit(after2)) if u}
        out.setdefault(value, set()).update(units)
    return out


def numbers(text: str) -> set[str]:
    return set(figures(text))


def is_grounded(expected: str, texts: list[str]) -> bool | None:
    """Does the document state the figures the expected answer states?

    A figure counts when the document has the same number next to the same
    unit ("2,000 running hours" supports "2,000 hours"; "350" in a part
    number does not support "350 C"). True when at least half the figures in
    the answer are supported, False when fewer are, None when the answer
    states no figure and so cannot be judged this way.
    """
    wanted = figures(expected)
    if not wanted:
        return None
    have: dict[str, set[str]] = {}
    for text in texts:
        for value, units in figures(text).items():
            have.setdefault(value, set()).update(units)
    supported = sum(
        1 for value, units in wanted.items()
        if value in have and (not units or units & have[value])
    )
    return supported * 2 >= len(wanted)


def canonical_title(title: str, titles: list[str]) -> str | None:
    """Map a paraphrased citation to the real document title, if close."""
    if title in titles:
        return title
    close = difflib.get_close_matches(title, titles, n=1, cutoff=0.75)
    return close[0] if close else None


def read_corpus(corpus_dir: Path, titles_by_slug: dict[str, str]) -> dict[str, str]:
    """{document title: body} for the documents present on disk."""
    out: dict[str, str] = {}
    for slug, title in titles_by_slug.items():
        path = corpus_dir / "markdown" / f"{slug}.md"
        if path.exists():
            out[title] = path.read_text("utf-8")
    return out
