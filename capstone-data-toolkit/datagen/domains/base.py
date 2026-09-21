"""The contract every domain generator satisfies.

Each of the five capstones needs the same four asset classes, which is what
lets one toolkit serve all of them and one rubric grade all of them:

  A. RAG corpus        -> the documents M3 indexes and M4 retrieves over
  B. Intake records    -> the raw inputs M1 parses into Pydantic objects
  C. Mock API tables   -> the state M2 tools read and M6 exposes over MCP
  D. Golden eval set   -> the 20 graded cases M8 scores against, adversarial
                          cases included

A domain module is mostly declarative: it supplies prompts, a schema sketch,
and a seed-table spec. The runner does the rest.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from faker import Faker

#: Frozen "now" for all generated dates. Change it and every relative date
#: in every domain shifts together, which is usually not what you want.
REFERENCE_NOW = datetime(2026, 8, 1, 9, 0)

from ..config import settings
from ..llm import ContentBlocked, complete, complete_json
from ..writers import (
    ensure_dir,
    write_csv,
    write_json,
    write_jsonl,
    write_markdown,
    write_pdf,
)


@dataclass
class DocSpec:
    """One document in the RAG corpus."""

    slug: str
    title: str
    section: str
    instruction: str


@dataclass
class EvalCase:
    """One graded case in the golden eval set.

    `category` drives partial-credit scoring in M8. The adversarial categories
    are the point: a system that scores well on `factual` and collapses on
    `injection` has not been evaluated, it has been flattered.
    """

    id: str
    question: str
    expected: str
    category: str  # factual | multi_hop | unanswerable | injection | guardrail
    must_cite: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    expected_route: str = "auto"  # auto | human_review | refuse


class DomainSpec(ABC):
    """Base class for a capstone domain generator."""

    #: Short identifier, used as the output subdirectory name.
    key: str
    #: Human-readable capstone name.
    name: str
    #: Persona the generating model adopts when writing corpus documents.
    author_persona: str
    #: Public datasets this domain's schemas were grounded against.
    public_sources: list[dict[str, str]] = []
    #: Categories the Data Sourcing Guide promises for this domain's eval set.
    #: build_eval_set warns when the model returns none of one.
    required_eval_categories: tuple[str, ...] = (
        "factual",
        "guardrail",
        "unanswerable",
    )

    def __init__(self) -> None:
        self.rng = random.Random(settings.seed)
        self.faker = Faker()
        Faker.seed(settings.seed)
        self._tables: dict[str, list[dict[str, Any]]] | None = None

    # ---------- deterministic dates ----------
    #
    # Faker's relative-date helpers resolve against the wall clock, so two runs
    # of the same seed on different days produce different data. Everything
    # here is anchored to a frozen reference instead, which is what makes
    # "same seed, same corpus, one rubric" actually true.

    def _offset(self, token: str) -> timedelta:
        token = token.strip().lower()
        if token in ("now", "today", "0"):
            return timedelta(0)
        sign = -1 if token.startswith("-") else 1
        value = int("".join(ch for ch in token if ch.isdigit()))
        unit = token[-1]
        days = {"d": 1, "w": 7, "m": 30, "y": 365}[unit]
        return timedelta(days=sign * value * days)

    def dt_between(self, start: str, end: str = "now") -> datetime:
        """Deterministic stand-in for Faker.date_time_between."""
        lo = REFERENCE_NOW + self._offset(start)
        hi = REFERENCE_NOW + self._offset(end)
        if hi < lo:
            lo, hi = hi, lo
        span = int((hi - lo).total_seconds())
        return lo + timedelta(seconds=self.rng.randint(0, max(span, 1)))

    def d_between(self, start: str, end: str = "today") -> date:
        return self.dt_between(start, end).date()

    def dob(self, minimum_age: int = 18, maximum_age: int = 88) -> date:
        days = self.rng.randint(minimum_age * 365, maximum_age * 365)
        return (REFERENCE_NOW - timedelta(days=days)).date()

    # ---------- Asset A: RAG corpus ----------

    @abstractmethod
    def doc_specs(self) -> list[DocSpec]:
        """Return the document plan for the RAG corpus."""

    def corpus_system_prompt(self) -> str:
        return (
            f"{self.author_persona}\n\n"
            "Write in the flat, clause-numbered register of a real internal "
            "policy document. Include specific numbers, thresholds, deadlines "
            "and named exceptions -- vague documents make retrieval evaluation "
            "meaningless because every chunk looks equally relevant. Never "
            "hedge with 'may vary' where a real document would state a figure. "
            "Use only invented organisation and person names. Do not reproduce "
            "text from any real published policy, standard, or regulation."
        )

    def planned_docs(self) -> list[DocSpec]:
        """The document plan actually used, honouring --corpus-docs.

        v1.0.0 built every spec regardless of the cap, so `--corpus-docs 4`
        silently generated the full set and burned the quota it was meant to
        save.
        """
        return self.doc_specs()[: settings.corpus_docs]

    def build_corpus(self, out_dir: Path) -> dict[str, Any]:
        docs_dir = ensure_dir(out_dir / "corpus")
        md_dir = ensure_dir(docs_dir / "markdown")
        pdf_dir = ensure_dir(docs_dir / "pdf")
        index: list[dict[str, Any]] = []
        skipped: list[str] = []
        blocked: list[str] = []

        for spec in self.planned_docs():
            md_path = md_dir / f"{spec.slug}.md"
            pdf_path = pdf_dir / f"{spec.slug}.pdf"

            # Resume. A run that dies at document 40 of 50 should cost 10 more
            # calls on retry, not 50.
            if settings.resume and md_path.exists() and pdf_path.exists():
                skipped.append(spec.slug)
                index.append(self._index_entry(spec, len(md_path.read_text("utf-8"))))
                continue

            try:
                body = complete(
                    spec.instruction,
                    system=self.corpus_system_prompt(),
                    temperature=0.85,
                )
            except ContentBlocked as exc:
                # Skip and keep going. One refused document must not destroy a
                # long run, but the user has to be told which one.
                blocked.append(f"{spec.slug} ({exc})")
                continue

            write_markdown(md_path, spec.title, body)
            write_pdf(pdf_path, spec.title, body)
            index.append(self._index_entry(spec, len(body)))

        write_json(docs_dir / "index.json", index)
        result: dict[str, Any] = {"count": len(index), "index": "corpus/index.json"}
        if skipped:
            result["resumed"] = len(skipped)
        if blocked:
            result["blocked"] = blocked
        return result

    def _index_entry(self, spec: DocSpec, chars: int) -> dict[str, Any]:
        return {
            "slug": spec.slug,
            "title": spec.title,
            "section": spec.section,
            "markdown": f"corpus/markdown/{spec.slug}.md",
            "pdf": f"corpus/pdf/{spec.slug}.pdf",
            "chars": chars,
        }

    # ---------- Asset B: intake records ----------

    @abstractmethod
    def intake_prompt(self, batch_size: int) -> str:
        """Prompt that yields a JSON array of raw intake records."""

    def build_intake(self, out_dir: Path) -> dict[str, Any]:
        target = settings.intake_records
        batch = 20
        rows: list[dict[str, Any]] = []
        attempts = 0
        empty_streak = 0

        # v1.0.0 looped `while len(rows) < target` with no exit. A model that
        # returns an empty array -- safety filter, malformed JSON, a bad free
        # tier day -- spun forever and burned the entire quota. Every loop that
        # depends on a model returning something needs a hard ceiling.
        max_attempts = max(settings.max_intake_attempts, (target // batch) * 3)

        while len(rows) < target and attempts < max_attempts:
            attempts += 1
            want = min(batch, target - len(rows))
            base_index = len(rows)  # capture before appending; v1.0.0 used
            # len(rows)+i while appending inside the loop, so IDs skipped
            # every other integer.
            try:
                got = complete_json(
                    self.intake_prompt(want),
                    system=(
                        "You generate realistic synthetic operational records for "
                        "software testing. Vary register, length, typos, and "
                        "completeness -- perfectly formed inputs teach nothing. "
                        "Roughly one in six records should be missing a field a "
                        "downstream parser needs."
                    ),
                )
            except ContentBlocked as exc:
                print(f"      intake batch refused by provider: {exc}")
                empty_streak += 1
                if empty_streak >= 3:
                    break
                continue

            if isinstance(got, dict):
                got = got.get("records", [])

            added = 0
            for rec in got or []:
                if isinstance(rec, dict):
                    rec.setdefault(
                        "record_id", f"{self.key.upper()}-{base_index + added:05d}"
                    )
                    rows.append(rec)
                    added += 1

            if added == 0:
                empty_streak += 1
                if empty_streak >= 3:
                    print(
                        "      three consecutive empty batches; stopping early "
                        "rather than looping."
                    )
                    break
            else:
                empty_streak = 0

        rows = rows[:target]
        write_jsonl(out_dir / "intake" / "records.jsonl", rows)

        result: dict[str, Any] = {
            "count": len(rows),
            "path": "intake/records.jsonl",
            "llm_calls": attempts,
        }
        if len(rows) < target:
            result["shortfall"] = target - len(rows)
            print(
                f"      WARNING: produced {len(rows)} of {target} intake records "
                f"in {attempts} attempts. Re-run to top up, or lower --intake."
            )
        return result

    # ---------- Asset C: mock API seed tables ----------

    @abstractmethod
    def seed_tables(self) -> dict[str, list[dict[str, Any]]]:
        """Deterministic tables backing the mock tool APIs."""

    #: Table names, declared so the CLI can display them without building
    #: 20,000 rows just to print a header line.
    table_names: tuple[str, ...] = ()

    def cached_seed_tables(self) -> dict[str, list[dict[str, Any]]]:
        """Build the seed tables once per run.

        v1.0.0 called seed_tables() twice -- once for a display line, once for
        the real build -- so the written data came from the *second* RNG draw.
        Caching alone would therefore change everyone's output, so by default
        we reproduce that discarded first draw. Pass --fresh-table-rng for the
        clean single-draw behaviour on a new project.
        """
        if self._tables is None:
            if settings.legacy_table_rng:
                self.seed_tables()  # discarded; preserves v1.0.0 byte output
            self._tables = self.seed_tables()
        return self._tables

    def build_seed_tables(self, out_dir: Path) -> dict[str, Any]:
        tables_dir = ensure_dir(out_dir / "mock_api")
        summary: dict[str, int] = {}
        for name, rows in self.cached_seed_tables().items():
            write_csv(tables_dir / f"{name}.csv", rows)
            write_json(tables_dir / f"{name}.json", rows)
            summary[name] = len(rows)
        return {"tables": summary, "dir": "mock_api/"}

    # ---------- Asset D: golden eval set ----------

    @abstractmethod
    def eval_prompt(self, n: int) -> str:
        """Prompt that yields graded eval cases grounded in the corpus."""

    @abstractmethod
    def handwritten_eval_cases(self) -> list[EvalCase]:
        """Adversarial cases written by hand, not by a model.

        A model asked to attack its own corpus produces polite attacks. The
        cases that actually break your system are written by a person who
        wants it to fail.
        """

    def build_eval_set(self, out_dir: Path, corpus_titles: list[str]) -> dict[str, Any]:
        hand = self.handwritten_eval_cases()
        need = max(0, settings.eval_items - len(hand))
        generated: list[EvalCase] = []

        if need:
            raw = complete_json(
                self.eval_prompt(need).replace(
                    "{{CORPUS_TITLES}}", "\n".join(f"- {t}" for t in corpus_titles)
                ),
                system=(
                    "You write evaluation cases for a retrieval-augmented "
                    "system. Every expected answer must be answerable from the "
                    "listed documents alone, except where the category is "
                    "'unanswerable', in which case the correct behaviour is an "
                    "explicit refusal to answer."
                ),
            )
            if isinstance(raw, dict):
                raw = raw.get("cases", [])
            for i, case in enumerate(raw or []):
                if not isinstance(case, dict):
                    continue
                generated.append(
                    EvalCase(
                        id=f"{self.key.upper()}-EV-{len(hand)+i+1:03d}",
                        question=str(case.get("question", "")).strip(),
                        expected=str(case.get("expected", "")).strip(),
                        category=str(case.get("category", "factual")),
                        must_cite=list(case.get("must_cite", []) or []),
                        must_not_contain=list(case.get("must_not_contain", []) or []),
                        expected_route=str(case.get("expected_route", "auto")),
                    )
                )

        cases = hand + generated[:need]
        payload = [c.__dict__ for c in cases]
        write_json(out_dir / "eval" / "golden_set.json", payload)

        by_cat: dict[str, int] = {}
        for c in cases:
            by_cat[c.category] = by_cat.get(c.category, 0) + 1

        result: dict[str, Any] = {
            "count": len(cases),
            "by_category": by_cat,
            "path": "eval/golden_set.json",
        }
        warnings = self._check_distribution(by_cat, len(cases))
        if warnings:
            result["distribution_warnings"] = warnings
            for w in warnings:
                print(f"      eval set: {w}")
        return result

    def _check_distribution(self, by_cat: dict[str, int], total: int) -> list[str]:
        """Warn when the model ignored the requested category mix.

        The Data Sourcing Guide promises a specific distribution per domain.
        Nothing enforced it in v1.0.0, so a model that returned twenty factual
        questions produced an eval set that looked complete and tested nothing.
        """
        problems: list[str] = []
        if total == 0:
            return ["no cases generated"]

        for cat in self.required_eval_categories:
            if by_cat.get(cat, 0) == 0:
                problems.append(
                    f"no '{cat}' cases -- the guide expects some; "
                    f"re-run `--only eval` or add them by hand"
                )

        factual = by_cat.get("factual", 0)
        if factual / total > 0.65:
            problems.append(
                f"{factual}/{total} cases are 'factual'; the model likely ignored "
                f"the requested mix. A set this shape will not surface guardrail "
                f"or grounding failures."
            )
        return problems

