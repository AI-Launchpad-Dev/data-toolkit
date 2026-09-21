"""Offline stub provider.

Every P0 bug in v1.0.0 lived behind an API call and survived because the
LLM-dependent paths were never exercised. This module makes those paths
testable without a key, including the failure shapes a free tier actually
produces: refusals, empty batches, short batches, and malformed JSON.

Use it in your own work too -- `python -m tests.run_offline` generates a full
dataset with no provider at all, which is a fast way to check that a change to
a domain module has not broken anything.
"""

from __future__ import annotations

from typing import Any, Callable

import datagen.domains.base as base
import datagen.llm as llm
from datagen.llm import ContentBlocked

CALLS: dict[str, int] = {"complete": 0, "complete_json": 0}

#: The genuine implementations, captured before any monkeypatching, so tests
#: that exercise the real provider layer can restore them.
_REAL = {"complete": llm.complete, "complete_json": llm.complete_json}


def uninstall() -> None:
    """Restore the real LLM functions."""
    _patch(_REAL["complete"], _REAL["complete_json"])

_DOC_BODY = (
    "## 1.1 Scope\n\nThis standard applies to all sites. The floor is 1.25x "
    "and the notice period is 30 days.\n\n## 1.2 Exceptions\n\nThree "
    "documented exceptions apply, each requiring named sign-off.\n"
)


def reset() -> None:
    CALLS["complete"] = 0
    CALLS["complete_json"] = 0


def _eval_payload(n: int, categories: list[str]) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        out.append(
            {
                "question": f"Question {i}?",
                "expected": f"Answer {i}.",
                "category": categories[i % len(categories)],
                "must_cite": ["Doc A"],
                "must_not_contain": [],
                "expected_route": "auto",
            }
        )
    return out


def install(
    mode: str = "happy",
    *,
    eval_categories: list[str] | None = None,
    block_slugs: tuple[str, ...] = (),
) -> None:
    """Monkeypatch the LLM layer.

    modes:
      happy        -- full batches, mixed eval categories
      empty_batch  -- intake always returns []  (v1.0.0: infinite loop)
      short_batch  -- intake returns 1 record per call
      dict_wrapped -- intake returns {"records": [...]} instead of a list
      blocked      -- provider refuses everything
      all_factual  -- eval returns only 'factual' cases
    """
    cats = eval_categories or [
        "factual",
        "multi_hop",
        "guardrail",
        "unanswerable",
        "injection",
        "bias_probe",
    ]
    if mode == "all_factual":
        cats = ["factual"]

    def fake_complete(prompt, *, system=None, temperature=None, provider=None):
        CALLS["complete"] += 1
        if mode == "blocked":
            raise ContentBlocked("stub refusal")
        for slug in block_slugs:
            if slug in prompt or slug.replace("-", " ") in prompt.lower():
                raise ContentBlocked(f"stub refusal for {slug}")
        return _DOC_BODY

    def fake_complete_json(prompt, *, system=None, temperature=None):
        CALLS["complete_json"] += 1
        if "evaluation cases" in prompt:
            return _eval_payload(40, cats)
        if mode == "blocked":
            raise ContentBlocked("stub refusal")
        if mode == "empty_batch":
            return []
        if mode == "short_batch":
            return [{"raw_text": "one"}]
        if mode == "dict_wrapped":
            return {"records": [{"raw_text": f"m{i}"} for i in range(20)]}
        return [
            {"raw_text": f"message {i}", "ground_truth": {"urgency": "Routine"}}
            for i in range(20)
        ]

    _patch(fake_complete, fake_complete_json)


def _patch(c: Callable[..., Any], cj: Callable[..., Any]) -> None:
    llm.complete = c  # type: ignore[assignment]
    llm.complete_json = cj  # type: ignore[assignment]
    base.complete = c  # type: ignore[assignment]
    base.complete_json = cj  # type: ignore[assignment]
