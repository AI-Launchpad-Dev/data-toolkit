"""Check that a generated dataset is complete and correctly shaped.

Run it after `generate.py`, from inside capstone-data-toolkit/:

    python -m tests.validate_data --domain plantguard
    python -m tests.validate_data --domain all

It reads the files under data/<domain>/ and compares them with what this
version of the toolkit is supposed to produce: every corpus document present
as markdown and PDF, every intake record carrying its fields, every mock API
table with the right columns, types and row counts, the eval set with its
hand-written cases, and a manifest describing the lot. No API key, no
network, nothing written.

Three result levels:

    PASS  as expected
    NOTE  a known limit of the default tables, with what to use instead
    WARN  usable, but not what a fresh run of this version would produce
    FAIL  missing or malformed; fix it before you build on the data

Exit status is 1 if anything FAILs (or WARNs, with --strict), so the command
works in CI.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datagen import __version__  # noqa: E402
from datagen.config import settings  # noqa: E402
from datagen.domains import REGISTRY  # noqa: E402
from datagen.grounding import GROUNDED_CATEGORIES, is_grounded  # noqa: E402

STAGES = ("manifest", "corpus", "intake", "tables", "eval")
EVAL_FIELDS = (
    "id",
    "question",
    "expected",
    "category",
    "must_cite",
    "must_not_contain",
    "expected_route",
)
ROUTES = {"auto", "human_review", "refuse"}
TYPE_NAMES = {str: "str", bool: "bool", int: "int", float: "float", type(None): "null"}


@dataclass
class Finding:
    level: str  # PASS | NOTE | WARN | FAIL
    section: str
    message: str
    fix: str = ""


@dataclass
class Report:
    key: str
    path: Path
    findings: list[Finding] = field(default_factory=list)

    def ok(self, section: str, message: str) -> None:
        self.findings.append(Finding("PASS", section, message))

    def note(self, section: str, message: str, fix: str = "") -> None:
        """A known limit of the default tables: worth reading, not a fault."""
        self.findings.append(Finding("NOTE", section, message, fix))

    def warn(self, section: str, message: str, fix: str = "") -> None:
        self.findings.append(Finding("WARN", section, message, fix))

    def fail(self, section: str, message: str, fix: str = "") -> None:
        self.findings.append(Finding("FAIL", section, message, fix))

    def count(self, level: str) -> int:
        return sum(f.level == level for f in self.findings)

    def tally(self) -> str:
        notes = f"{self.count('NOTE')} notes, " if self.count("NOTE") else ""
        return (f"{self.count('PASS')} passed, {notes}{self.count('WARN')} warnings, "
                f"{self.count('FAIL')} failed")

    def has(self, level: str, text: str = "") -> bool:
        return any(f.level == level and text in f.message for f in self.findings)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _short(items: list[str], limit: int = 6) -> str:
    items = list(items)
    more = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(items[:limit]) + more


def _type_name(value: Any) -> str:
    return TYPE_NAMES.get(type(value), type(value).__name__)


def reference_tables(key: str, seed: int) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """What this toolkit version builds for `seed`, in both table modes.

    Round-tripped through JSON so it compares equal to what is read from disk.
    """
    saved = (settings.seed, settings.legacy_table_rng)
    out = {}
    try:
        for mode, legacy in (("default", True), ("--fresh-table-rng", False)):
            settings.seed, settings.legacy_table_rng = seed, legacy
            built = REGISTRY[key]().cached_seed_tables()
            out[mode] = json.loads(json.dumps(built, default=str))
    finally:
        settings.seed, settings.legacy_table_rng = saved
    return out


# --------------------------------------------------------------------- manifest
def check_manifest(rep: Report) -> dict[str, Any]:
    path = rep.path / "manifest.json"
    if not path.exists():
        rep.fail("manifest", "manifest.json is missing",
                 f"python generate.py --domain {rep.key} --only tables")
        return {}
    try:
        manifest = _load_json(path)
    except ValueError as exc:
        rep.fail("manifest", f"manifest.json is not valid JSON ({exc})")
        return {}
    rep.ok("manifest", f"manifest.json present (seed {manifest.get('seed')}, "
                       f"toolkit {manifest.get('toolkit_version')})")
    if manifest.get("complete") is not True:
        rep.warn("manifest", "the last run did not finish (complete: false)",
                 f"python generate.py --domain {rep.key}   # resumes where it stopped")
    if manifest.get("toolkit_version") != __version__:
        rep.warn(
            "manifest",
            f"generated by toolkit {manifest.get('toolkit_version')}, you are "
            f"running {__version__}",
            "see 'Do I need to regenerate?' in CHANGELOG.md",
        )
    if manifest.get("contains_real_personal_data") is not False:
        rep.fail("manifest", "contains_real_personal_data is not false")
    return manifest


# ----------------------------------------------------------------------- corpus
def check_corpus(rep: Report, corpus_docs: int | None) -> dict[str, str]:
    """Returns {slug: markdown text} for the documents found."""
    spec = REGISTRY[rep.key]()
    docs = spec.doc_specs()[: corpus_docs or None]
    root = rep.path / "corpus"
    rerun = f"python generate.py --domain {rep.key} --only corpus"
    if not root.exists():
        rep.fail("corpus", "no corpus/ folder: the corpus was never generated", rerun)
        return {}

    texts: dict[str, str] = {}
    no_md, no_pdf, bad_pdf, empty, short, untitled = [], [], [], [], [], []
    for doc in docs:
        md = root / "markdown" / f"{doc.slug}.md"
        pdf = root / "pdf" / f"{doc.slug}.pdf"
        if md.exists():
            text = md.read_text("utf-8")
            texts[doc.slug] = text
            body = text.split("\n", 1)[1].strip() if "\n" in text else ""
            if len(body) < 100:
                empty.append(doc.slug)
            elif len(body) < 1500:
                short.append(f"{doc.slug} ({len(body)} chars)")
            if not text.startswith(f"# {doc.title}"):
                untitled.append(doc.slug)
        else:
            no_md.append(doc.slug)
        if not pdf.exists():
            no_pdf.append(doc.slug)
        elif pdf.stat().st_size < 800 or pdf.read_bytes()[:4] != b"%PDF":
            bad_pdf.append(doc.slug)

    missing = sorted(set(no_md) | set(no_pdf))
    if missing:
        rep.fail(
            "corpus",
            f"{len(docs) - len(missing)} of {len(docs)} documents complete; "
            f"missing: {_short(missing)}",
            f"{rerun}   # finished documents are skipped. A document the "
            f"provider keeps refusing: add --provider ollama",
        )
    else:
        rep.ok("corpus", f"all {len(docs)} documents present as markdown and PDF")
    if bad_pdf:
        rep.fail("corpus", f"unreadable PDF: {_short(bad_pdf)}",
                 "delete those files and re-run " + rerun)
    if empty:
        rep.fail("corpus", f"document has no content: {_short(empty)}",
                 "delete the .md and .pdf of those documents and re-run " + rerun)
    if short:
        rep.warn("corpus", f"unusually short document: {_short(short)}",
                 "a full document is several thousand characters; regenerate if "
                 "retrieval over it will matter")
    if untitled:
        rep.warn("corpus", f"first line is not '# <title>': {_short(untitled)}")

    bodies: dict[str, list[str]] = {}
    for slug, text in texts.items():
        bodies.setdefault(text.split("\n", 1)[-1].strip(), []).append(slug)
    clones = [slugs for slugs in bodies.values() if len(slugs) > 1]
    if clones:
        rep.warn("corpus", f"identical text in: {_short(clones[0])}",
                 "each document should differ; regenerate the duplicates")

    index_path = root / "index.json"
    if not index_path.exists():
        rep.fail("corpus", "corpus/index.json is missing", rerun)
    else:
        try:
            listed = {e.get("slug") for e in _load_json(index_path)}
            unlisted = sorted(set(texts) - listed)
            if unlisted:
                rep.fail("corpus", f"index.json does not list: {_short(unlisted)}", rerun)
            else:
                rep.ok("corpus", f"index.json lists all {len(texts)} documents")
        except (ValueError, AttributeError) as exc:
            rep.fail("corpus", f"index.json is not valid ({exc})", rerun)

    planned = {d.slug for d in spec.doc_specs()}
    strays = sorted(p.stem for p in (root / "markdown").glob("*.md")
                    if p.stem not in planned) if (root / "markdown").exists() else []
    if strays:
        rep.warn("corpus", f"documents this version does not generate: {_short(strays)}",
                 "left over from another version or added by hand; remove them "
                 "if you did not write them")
    return texts


# ----------------------------------------------------------------------- intake
def check_intake(rep: Report, expected: int) -> list[dict[str, Any]]:
    spec = REGISTRY[rep.key]()
    path = rep.path / "intake" / "records.jsonl"
    rerun = f"python generate.py --domain {rep.key} --only intake"
    if not path.exists():
        rep.fail("intake", "intake/records.jsonl is missing", rerun)
        return []
    records, bad = [], 0
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            records.append(row) if isinstance(row, dict) else None
            bad += not isinstance(row, dict)
        except ValueError:
            bad += 1
    if bad:
        rep.fail("intake", f"{bad} line(s) are not JSON objects", rerun + " --no-resume")
    if not records:
        rep.fail("intake", "records.jsonl holds no records", rerun)
        return []
    if len(records) < expected:
        rep.warn("intake", f"{len(records)} of {expected} records",
                 rerun + "   # tops up, keeping what you have")
    else:
        rep.ok("intake", f"{len(records)} records, all valid JSON")

    ids = [r.get("record_id") for r in records]
    if None in ids or len(set(ids)) != len(ids):
        rep.fail("intake", "record_id is missing or repeated", rerun + " --no-resume")
    else:
        rep.ok("intake", "every record has a unique record_id")

    n = len(records)
    with_truth = sum(isinstance(r.get("ground_truth"), dict) for r in records)
    if with_truth < 0.5 * n:
        rep.fail("intake", f"only {with_truth} of {n} records carry a ground_truth object",
                 rerun + " --no-resume")
    elif with_truth < 0.95 * n:
        rep.warn("intake", f"{n - with_truth} of {n} records have no ground_truth object")
    else:
        rep.ok("intake", f"ground_truth present on {with_truth} of {n} records")

    def coverage(fields: tuple[str, ...], rows: list[dict[str, Any]], what: str) -> None:
        if not fields or not rows:
            return
        thin = [f"{f} ({100 * sum(f in r for r in rows) // len(rows)}%)"
                for f in fields if sum(f in r for r in rows) < 0.8 * len(rows)]
        if thin:
            rep.warn("intake", f"{what} present in under 80% of records: {_short(thin)}",
                     "the model skipped these keys; regenerate with " + rerun
                     + " --no-resume, or make them optional in your Pydantic model")
        else:
            rep.ok("intake", f"all {len(fields)} {what} present "
                             f"({', '.join(fields)})")

    coverage(spec.intake_fields, records, "record fields")
    coverage(spec.intake_truth_fields,
             [r["ground_truth"] for r in records if isinstance(r.get("ground_truth"), dict)],
             "ground_truth fields")
    return records


# ----------------------------------------------------------------------- tables
def check_tables(rep: Report, seed: int) -> dict[str, list[dict[str, Any]]]:
    """Returns the tables as read from disk."""
    spec = REGISTRY[rep.key]()
    root = rep.path / "mock_api"
    rerun = f"python generate.py --domain {rep.key} --only tables"
    if not root.exists():
        rep.fail("tables", "no mock_api/ folder: the tables were never generated", rerun)
        return {}
    reference = reference_tables(rep.key, seed)
    expect = reference["default"]

    missing = [t for t in spec.table_names
               if not (root / f"{t}.json").exists() or not (root / f"{t}.csv").exists()]
    if missing:
        rep.fail("tables", f"{len(spec.table_names) - len(missing)} of "
                           f"{len(spec.table_names)} tables present; missing: {_short(missing)}",
                 rerun + "   # adds missing tables, existing ones are rewritten identically")
    else:
        rep.ok("tables", f"all {len(spec.table_names)} tables present as CSV and JSON")

    disk: dict[str, list[dict[str, Any]]] = {}
    for name in spec.table_names:
        path = root / f"{name}.json"
        if not path.exists():
            continue
        try:
            rows = _load_json(path)
            assert isinstance(rows, list) and rows and isinstance(rows[0], dict)
        except (ValueError, AssertionError):
            rep.fail("tables", f"{name}.json is not a non-empty list of objects", rerun)
            continue
        disk[name] = rows
    # Which of the two table modes was this generated in? Compare against that.
    same_as = next(
        (mode for mode, built in reference.items()
         if disk and all(disk[t] == built.get(t) for t in disk)),
        None,
    )
    if same_as is None and disk:
        # Not identical to either: judge row counts against the closer one.
        same_len = {mode: sum(len(disk[t]) == len(built.get(t, [])) for t in disk)
                    for mode, built in reference.items()}
        expect = reference[max(same_len, key=lambda m: same_len[m])]
    elif same_as:
        expect = reference[same_as]

    wrong_cols, wrong_types, wrong_rows, csv_bad = [], [], [], []
    for name, rows in disk.items():
        want_cols = list(expect[name][0].keys())
        if list(rows[0].keys()) != want_cols or any(r.keys() != rows[0].keys() for r in rows):
            got = set().union(*(r.keys() for r in rows))
            lost, extra = sorted(set(want_cols) - got), sorted(got - set(want_cols))
            wrong_cols.append(
                f"{name} (" + "; ".join(
                    x for x in (f"missing {_short(lost)}" if lost else "",
                                f"unexpected {_short(extra)}" if extra else "",
                                "" if lost or extra else "column order differs") if x) + ")")
        else:
            for col in want_cols:
                allowed = {_type_name(r[col]) for r in expect[name]}
                if "float" in allowed:
                    allowed.add("int")
                seen = {_type_name(r[col]) for r in rows} - allowed
                if seen:
                    wrong_types.append(f"{name}.{col} holds {'/'.join(sorted(seen))}, "
                                       f"expected {'/'.join(sorted(allowed))}")
        if len(rows) != len(expect[name]):
            wrong_rows.append(f"{name} ({len(rows):,}, expected {len(expect[name]):,})")
        csv_path = root / f"{name}.csv"
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, [])
                lines = sum(1 for _ in reader)
            if header != list(rows[0].keys()) or lines != len(rows):
                csv_bad.append(name)

    if wrong_cols:
        rep.fail("tables", "columns differ from the schema: " + _short(wrong_cols, 4), rerun)
    elif disk:
        rep.ok("tables", f"columns match the schema in all {len(disk)} tables "
                         f"({sum(len(v[0]) for v in disk.values())} columns)")
    if wrong_types:
        rep.fail("tables", "wrong value type: " + _short(wrong_types, 4), rerun)
    elif disk and not wrong_cols:
        rep.ok("tables", "every column holds the expected type")
    if wrong_rows:
        rep.warn("tables", "row count differs: " + _short(wrong_rows, 4),
                 f"expected counts are for seed {seed}; " + rerun)
    elif disk:
        rep.ok("tables", f"row counts as expected ({sum(len(v) for v in disk.values()):,} rows)")
    if csv_bad:
        rep.fail("tables", "CSV and JSON disagree: " + _short(csv_bad), rerun)
    elif disk:
        rep.ok("tables", "CSV copies match the JSON copies")

    # Foreign keys. A table owns a key when its first column is unique.
    owners: dict[str, set[Any]] = {}
    for rows in disk.values():
        first = next(iter(rows[0]))
        values = [r.get(first) for r in rows]
        if len(set(values)) == len(values):
            owners[first] = set(values)
    dangling = []
    for name, rows in disk.items():
        first = next(iter(rows[0]))
        for col in rows[0]:
            if col in owners and col != first:
                lost = {r.get(col) for r in rows if r.get(col) is not None} - owners[col]
                if lost:
                    dangling.append(f"{name}.{col} ({len(lost)} unknown)")
    for source, target in spec.references.items():
        (st, sc), (tt, tc) = source.split("."), target.split(".")
        if st in disk and tt in disk and sc in disk[st][0] and tc in disk[tt][0]:
            known = {r.get(tc) for r in disk[tt]}
            lost = {r.get(sc) for r in disk[st] if r.get(sc) is not None} - known
            if lost:
                dangling.append(f"{source} ({len(lost)} unknown)")
    if dangling:
        rep.fail("tables", "references that resolve to nothing: " + _short(dangling, 4), rerun)
    elif disk:
        rep.ok("tables", "every ID that refers to another table resolves")

    if same_as:
        rep.ok("tables", f"values identical to a fresh build (seed {seed}, {same_as} mode)")
    else:
        if disk and not (wrong_cols or wrong_types):
            rep.warn(
                "tables",
                f"values differ from a fresh build with seed {seed}",
                "expected if you edited the tables, changed the seed after "
                "generating, or use another faker version; otherwise " + rerun,
            )
    strays = sorted(p.stem for p in root.glob("*.json") if p.stem not in spec.table_names)
    if strays:
        rep.warn("tables", f"tables this version does not generate: {_short(strays)}")
    return disk


# ------------------------------------------------------------------------- eval
def check_eval(rep: Report, expected: int, texts: dict[str, str] | None = None) -> None:
    spec = REGISTRY[rep.key]()
    path = rep.path / "eval" / "golden_set.json"
    rerun = f"python generate.py --domain {rep.key} --only eval --no-resume"
    if not path.exists():
        rep.fail("eval", "eval/golden_set.json is missing",
                 f"python generate.py --domain {rep.key} --only eval")
        return
    try:
        cases = _load_json(path)
        assert isinstance(cases, list) and all(isinstance(c, dict) for c in cases)
    except (ValueError, AssertionError):
        rep.fail("eval", "golden_set.json is not a list of cases", rerun)
        return
    if not cases:
        rep.fail("eval", "golden_set.json holds no cases", rerun)
        return
    if len(cases) < expected:
        rep.warn("eval", f"{len(cases)} of {expected} cases", rerun)
    else:
        rep.ok("eval", f"{len(cases)} cases")

    lacking = sorted({f for c in cases for f in EVAL_FIELDS if f not in c})
    ids = [c.get("id") for c in cases]
    if lacking:
        rep.fail("eval", f"cases lack fields: {_short(lacking)}", rerun)
    elif len(set(ids)) != len(ids):
        rep.fail("eval", "case ids are repeated", rerun)
    else:
        rep.ok("eval", f"every case has all {len(EVAL_FIELDS)} fields and a unique id")

    by_id = {c.get("id"): c for c in cases}
    hand = [c.__dict__ for c in spec.handwritten_eval_cases()]
    absent = [c["id"] for c in hand if c["id"] not in by_id]
    stale = [c["id"] for c in hand if c["id"] in by_id and by_id[c["id"]] != c]
    if absent:
        rep.fail("eval", f"hand-written adversarial cases missing: {_short(absent)}", rerun)
    if stale:
        rep.warn("eval", f"hand-written cases differ from this version: {_short(stale)}",
                 rerun + "   # v1.0.2 corrected the must_not_contain lists")
    if not absent and not stale:
        rep.ok("eval", f"all {len(hand)} hand-written adversarial cases present and current")

    cats = {c.get("category") for c in cases}
    no_cat = [c for c in spec.required_eval_categories if c not in cats]
    if no_cat:
        rep.warn("eval", f"no cases in category: {_short(no_cat)}",
                 rerun + "   # or add them by hand")
    else:
        rep.ok("eval", "categories covered: " + ", ".join(spec.required_eval_categories))
    odd = sorted({str(c.get("expected_route")) for c in cases} - ROUTES)
    if odd:
        rep.warn("eval", f"expected_route outside auto/human_review/refuse: {_short(odd)}")

    titles = {d.title for d in spec.doc_specs()}
    unknown = [c["id"] for c in cases
               if any(t not in titles for t in c.get("must_cite") or [])]
    if unknown:
        rep.warn("eval", f"{len(unknown)} case(s) cite a document title that is not "
                         f"in the corpus: {_short(unknown)}",
                 "the model paraphrased a title; correct must_cite in those cases "
                 "or your citation score will be wrong")
    else:
        rep.ok("eval", "every must_cite title is a real corpus document")

    # Is each expected answer actually in the document it cites?
    if texts:
        by_title = {d.title: texts[d.slug] for d in spec.doc_specs() if d.slug in texts}
        hand_ids = {c["id"] for c in hand}
        judged = invented = 0
        loose = []
        for c in cases:
            if c.get("id") in hand_ids or c.get("category") not in GROUNDED_CATEGORIES:
                continue
            cited = [by_title[t] for t in c.get("must_cite") or [] if t in by_title]
            verdict = is_grounded(str(c.get("expected", "")), cited or list(by_title.values()))
            judged += verdict is not None
            if verdict is False:
                invented += 1
                loose.append(c["id"])
        if loose:
            rep.warn(
                "eval",
                f"{invented} model-written case(s) expect a figure that the cited "
                f"document does not contain: {_short(loose)}",
                rerun + "   # v1.0.4 writes these cases from the corpus text; "
                        "before that the model saw only titles and invented the figures",
            )
        elif judged:
            rep.ok("eval", f"expected figures of {judged} model-written cases appear "
                           f"in the documents they cite")


# -------------------------------------------------------------- domain extras
def _plantguard(rep: Report, texts: dict[str, str], records: list[dict[str, Any]],
                tables: dict[str, list[dict[str, Any]]]) -> None:
    if not tables:
        return
    assets = {a["asset_tag"]: a for a in tables.get("assets", [])}
    parts = {p["part_number"] for p in tables.get("inventory", [])}

    crit = tables.get("asset_criticality")
    if crit and assets:
        safety = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        env = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
        cls = {"A": 0, "B": 1, "C": 2}

        def cost(rate: float) -> int:
            return 0 if rate >= 30_000 else 1 if rate >= 10_000 else 2

        wrong = [r["asset_tag"] for r in crit
                 if min(safety.get(r["safety_risk"], 9), env.get(r["environmental_impact"], 9),
                        cost(r["downtime_cost_per_hour_inr"])) != cls.get(r["criticality"])
                 or assets.get(r["asset_tag"], {}).get("criticality") != r["criticality"]]
        if wrong or len(crit) != len(assets):
            rep.fail("plantguard", "criticality does not follow from its three factors: "
                     + _short(wrong), f"python generate.py --domain {rep.key} --only tables")
        else:
            rep.ok("plantguard", f"criticality of all {len(crit)} assets follows from safety "
                                 f"risk, environmental impact and downtime cost")
    techs = {t["technician_id"] for t in tables.get("technicians", [])}
    if techs and tables.get("work_orders"):
        skills = sorted({t["primary_skill"] for t in tables["technicians"]})
        rep.ok("plantguard", f"{len(techs)} technicians across {len(skills)} skills "
                             f"({', '.join(skills)}); every work order's technician exists")

    if records and assets:
        tagged = [r for r in records if r.get("asset_tag")]
        unknown = [r for r in tagged if r["asset_tag"] not in assets]
        if tagged and len(unknown) > 0.1 * len(tagged):
            rep.warn("plantguard", f"{len(unknown)} of {len(tagged)} intake events name an "
                                   f"asset_tag that is not in the assets table",
                     f"python generate.py --domain {rep.key} --only intake --no-resume   "
                     f"# records generated before v1.0.3 invented their asset tags")
        elif tagged:
            rep.ok("plantguard", f"intake events name real assets "
                                 f"({len(tagged) - len(unknown)} of {len(tagged)})")

    manuals = {s: t for s, t in texts.items() if s.startswith("manual-")}
    if manuals and parts:
        regen = (f"python generate.py --domain {rep.key} --only corpus --no-resume   "
                 f"# rewrites all {len(texts)} documents; or keep them and take part "
                 f"numbers from mock_api/inventory")
        none = [s for s, t in manuals.items()
                if not set(re.findall(r"VPW-P-\d{5}", t)) & parts]
        if none:
            rep.warn("plantguard", f"manuals that cite no part from the inventory table: "
                                   f"{_short(sorted(none))}", regen)
        else:
            rep.ok("plantguard", f"all {len(manuals)} manuals cite real inventory part numbers")
    plan = texts.get("maintenance-planning")
    if plan:
        if all(w in plan for w in ("HIGH", "CRITICAL", "MAJOR", "MINOR")):
            rep.ok("plantguard", "maintenance planning document carries the criticality matrix")
        else:
            rep.warn("plantguard", "maintenance planning document does not state the "
                                   "criticality matrix",
                     f"python generate.py --domain {rep.key} --only corpus --no-resume   "
                     f"# or keep it and use mock_api/criticality_matrix as the source of truth")


def _careflow(rep: Report, texts: dict[str, str], records: list[dict[str, Any]],
              tables: dict[str, list[dict[str, Any]]]) -> None:
    regen = (f"python generate.py --domain {rep.key} --only corpus --no-resume   "
             f"# or keep the documents and trust the mock_api tables")
    doc = texts.get("copay-schedule")
    if doc and tables.get("plans"):
        absent = [p["plan_code"] for p in tables["plans"] if p["plan_code"] not in doc]
        if absent:
            rep.warn("careflow", f"cost-share schedule does not mention: {_short(absent)}", regen)
        else:
            rep.ok("careflow", "cost-share schedule covers every plan in the plans table")
    matrix = texts.get("preauth-matrix")
    procedures = tables.get("procedures")
    if matrix and procedures:
        named = [p for p in procedures
                 if p["procedure_code"] in matrix or p["procedure_name"] in matrix]
        if len(named) < 0.8 * len(procedures):
            rep.warn("careflow", f"pre-authorisation matrix names {len(named)} of "
                                 f"{len(procedures)} procedures in the procedures table", regen)
        else:
            rep.ok("careflow", f"pre-authorisation matrix names {len(named)} of "
                               f"{len(procedures)} procedures")

    patients = {p["patient_ref"]: p for p in tables.get("patients", [])}
    details = tables.get("referral_details")
    if details and patients and tables.get("preauth_rules"):
        rule = {(r["procedure_code"], r["plan_code"]): r for r in tables["preauth_rules"]}
        ref = {r["referral_id"]: r for r in tables["referrals"]}
        wrong = [d["referral_id"] for d in details
                 if rule[(d["procedure_code"], patients[ref[d["referral_id"]]["patient_ref"]]
                          ["plan_code"])]["preauth_required"]
                 != ref[d["referral_id"]]["preauth_required"]]
        if wrong:
            rep.fail("careflow", "referral pre-authorisation flag contradicts the rule for "
                                 f"its procedure and plan: {_short(wrong)}",
                     f"python generate.py --domain {rep.key} --only tables")
        else:
            rep.ok("careflow", f"all {len(details)} referrals agree with the "
                               f"pre-authorisation rule for their procedure and plan")

    providers = {p["provider_id"]: p["specialty"] for p in tables.get("providers", [])}
    if providers and tables.get("appointments"):
        off = sum(providers.get(a["provider_id"]) != a["specialty"]
                  for a in tables["appointments"])
        if off:
            rep.note("careflow", f"{off} of {len(tables['appointments'])} past appointments "
                                 f"pair a provider with a specialty that is not theirs",
                     "providers.specialty and appointment_slots for scheduling; the "
                     "appointments table drew the two at random. --fresh-table-rng "
                     "makes them agree")
    plans = {p["plan_code"]: p["annual_deductible_usd"] for p in tables.get("plans", [])}
    if plans and patients:
        over = sum(p["deductible_met_usd"] > plans[p["plan_code"]] for p in patients.values())
        if over:
            rep.note("careflow", f"{over} patients have deductible_met_usd above their "
                                 f"plan's deductible",
                     "treat those as fully met, as the cost-share schedule says. "
                     "--fresh-table-rng caps them")

    if records and patients:
        tagged = [r for r in records if r.get("patient_ref")]
        unknown = [r for r in tagged if r["patient_ref"] not in patients]
        if tagged and len(unknown) > 0.1 * len(tagged):
            rep.warn("careflow", f"{len(unknown)} of {len(tagged)} intake messages name a "
                                 f"patient_ref that is not in the patients table",
                     f"python generate.py --domain {rep.key} --only intake --no-resume   "
                     f"# records generated before v1.0.4 invented their patient references")
        elif tagged:
            rep.ok("careflow", f"intake messages name registered patients "
                               f"({len(tagged) - len(unknown)} of {len(tagged)})")


def _lexops(rep: Report, texts: dict[str, str], records: list[dict[str, Any]],
            tables: dict[str, list[dict[str, Any]]]) -> None:
    regen = (f"python generate.py --domain {rep.key} --only corpus --no-resume   "
             f"# or keep the documents and trust mock_api/playbook_positions")
    clauses, risk = tables.get("contract_clauses"), tables.get("contract_risk")
    if clauses and risk:
        total: dict[str, int] = {}
        for c in clauses:
            total[c["contract_id"]] = total.get(c["contract_id"], 0) + c["risk_points"]
        wrong = [r["contract_id"] for r in risk
                 if min(100, total.get(r["contract_id"], -1)) != r["risk_score"]]
        if wrong:
            rep.fail("lexops", "risk score is not the sum of the contract's clause "
                               f"points: {_short(wrong)}",
                     f"python generate.py --domain {rep.key} --only tables")
        else:
            rep.ok("lexops", f"risk score of all {len(risk)} contracts equals the sum "
                             f"of their clause points")
        legacy = {c["contract_id"]: c["risk_score"] for c in tables.get("contracts", [])}
        differ = sum(legacy.get(r["contract_id"]) != r["risk_score"] for r in risk)
        if differ:
            rep.note("lexops", f"contracts.risk_score differs from contract_risk.risk_score "
                               f"on {differ} of {len(risk)} contracts",
                     "use contract_risk.risk_score: the column in contracts is a random "
                     "number kept for compatibility. --fresh-table-rng makes them equal")
    positions = tables.get("playbook_positions")
    scoring = texts.get("risk-scoring")
    if scoring and tables.get("clause_families"):
        families = [f["clause_family"] for f in tables["clause_families"]]
        named = [f for f in families if f.lower() in scoring.lower()]
        if len(named) < 6:
            rep.warn("lexops", f"risk scoring methodology names {len(named)} of "
                               f"{len(families)} clause families in clause_families", regen)
        else:
            rep.ok("lexops", f"risk scoring methodology names {len(named)} of "
                             f"{len(families)} clause families")
    if positions and texts:
        silent = [p["clause_type"] for p in positions
                  if f"clause-{p['clause_type']}" in texts
                  and p["named_deviation"].lower()
                  not in texts[f"clause-{p['clause_type']}"].lower()]
        if len(silent) > 3:
            rep.warn("lexops", "playbook sections that do not name their deviation from "
                               f"playbook_positions: {_short(silent)}", regen)
        else:
            rep.ok("lexops", "playbook sections name the deviations in playbook_positions")
    parties = {c["counterparty_id"] for c in tables.get("counterparties", [])}
    if records and parties:
        tagged = [r for r in records if r.get("counterparty_id")]
        unknown = [r for r in tagged if r["counterparty_id"] not in parties]
        if not tagged:
            rep.warn("lexops", "no intake request carries a counterparty_id",
                     f"python generate.py --domain {rep.key} --only intake --no-resume   "
                     f"# requests generated before v1.0.4 invented their counterparties")
        elif len(unknown) > 0.1 * len(tagged):
            rep.warn("lexops", f"{len(unknown)} of {len(tagged)} intake requests name a "
                               f"counterparty that is not in the counterparties table",
                     f"python generate.py --domain {rep.key} --only intake --no-resume")
        else:
            rep.ok("lexops", f"intake requests name real counterparties "
                             f"({len(tagged) - len(unknown)} of {len(tagged)})")


def _wealthpilot(rep: Report, texts: dict[str, str], records: list[dict[str, Any]],
                 tables: dict[str, list[dict[str, Any]]]) -> None:
    regen = (f"python generate.py --domain {rep.key} --only corpus --no-resume   "
             f"# or keep the documents and trust the mock_api tables")
    apps = {a["application_id"]: a for a in tables.get("loan_applications", [])}
    ref = {r["application_id"]: r for r in tables.get("underwriting_reference", [])}
    applicants = {a["applicant_id"]: a for a in tables.get("applicants", [])}
    if apps and ref and applicants:
        wrong = []
        for app_id, r in ref.items():
            app = apps[app_id]
            service = app["existing_annual_debt_service_inr"] + r["proposed_annual_debt_service_inr"]
            dscr = round(applicants[app["applicant_id"]]["ebitda_inr"] / service, 2)
            if abs(dscr - r["dscr"]) > 0.011 or r["meets_dscr_floor"] != (
                r["dscr"] >= r["sector_dscr_floor"]
            ):
                wrong.append(app_id)
        if wrong:
            rep.fail("wealthpilot", "DSCR in underwriting_reference does not follow from "
                                    f"the application's figures: {_short(wrong)}",
                     f"python generate.py --domain {rep.key} --only tables")
        else:
            rep.ok("wealthpilot", f"DSCR of all {len(ref)} applications equals EBITDA over "
                                  f"existing plus proposed debt service")

    statements = tables.get("bank_statements")
    if statements and applicants:
        per: dict[str, set[str]] = {}
        for st in statements:
            per.setdefault(st["applicant_id"], set()).add(st["month"])
        short = sum(len(per.get(a, ())) < min(18, applicants[a]["months_operating"])
                    for a in applicants)
        if short:
            rep.note("wealthpilot", f"{short} of {len(applicants)} applicants have fewer than "
                                    f"18 monthly bank statements ({len(applicants) - len(per)} "
                                    f"have none), and inflows are unrelated to revenue",
                     "--fresh-table-rng, which writes up to 18 consecutive months per "
                     "applicant, sized to the business; the default table is kept for "
                     "compatibility")
    people = {u["user_id"]: u for u in tables.get("signatories", [])}
    decisions = tables.get("past_decisions")
    if decisions and people:
        odd = sum(
            (d["outcome"] != "approved" and d["approved_amount_inr"] > 0)
            or (d["outcome"] == "approved" and d["approved_amount_inr"] == 0)
            or (people[d["human_signatory"]]["approval_limit_inr"] is not None
                and d["approved_amount_inr"] > people[d["human_signatory"]]["approval_limit_inr"])
            for d in decisions if d["human_signatory"] in people
        )
        if odd:
            rep.note("wealthpilot", f"{odd} of {len(decisions)} past decisions contradict "
                                    f"themselves (an amount on a decline, or a signatory "
                                    f"without authority for the amount)",
                     "treat past_decisions as history of mixed quality, or generate with "
                     "--fresh-table-rng")

    grading = texts.get("risk-grading")
    if grading and tables.get("risk_grades"):
        absent = [g["grade"] for g in tables["risk_grades"] if g["grade"] not in grading]
        if absent:
            rep.warn("wealthpilot", f"risk grading document does not mention: {_short(absent)}",
                     regen)
        else:
            rep.ok("wealthpilot", "risk grading document covers every grade in risk_grades")
    adverse = texts.get("adverse-action")
    if adverse and tables.get("reason_codes"):
        named = [c for c in tables["reason_codes"] if c["reason_code"] in adverse]
        if len(named) < 0.7 * len(tables["reason_codes"]):
            rep.warn("wealthpilot", f"adverse action standard names {len(named)} of "
                                    f"{len(tables['reason_codes'])} reason codes in reason_codes",
                     regen)
        else:
            rep.ok("wealthpilot", f"adverse action standard names {len(named)} of "
                                  f"{len(tables['reason_codes'])} reason codes")

    if records and apps:
        tagged = [r for r in records if r.get("application_id")]
        known = [r for r in tagged if r["application_id"] in apps]
        if tagged and len(known) < 0.9 * len(tagged):
            rep.warn("wealthpilot", f"{len(tagged) - len(known)} of {len(tagged)} intake "
                                    f"applications are not in the loan_applications table",
                     f"python generate.py --domain {rep.key} --only intake --no-resume   "
                     f"# applications generated before v1.0.4 were invented, with DSCRs "
                     f"the model computed itself")
        elif known:
            off = [r["application_id"] for r in known
                   if isinstance(r.get("ground_truth"), dict)
                   and r["ground_truth"].get("dscr") is not None
                   and not r["ground_truth"].get("missing_fields")
                   and abs(r["ground_truth"]["dscr"] - ref[r["application_id"]]["dscr"]) > 0.011]
            if off:
                rep.warn("wealthpilot", f"intake DSCR differs from underwriting_reference: "
                                        f"{_short(off)}",
                         f"python generate.py --domain {rep.key} --only intake --no-resume")
            else:
                rep.ok("wealthpilot", f"intake applications match loan_applications and their "
                                      f"DSCR labels match the reference ({len(known)} checked)")


def _shopsense(rep: Report, texts: dict[str, str], records: list[dict[str, Any]],
               tables: dict[str, list[dict[str, Any]]]) -> None:
    from datetime import date, datetime, timedelta

    regen = (f"python generate.py --domain {rep.key} --only corpus --no-resume   "
             f"# or keep the documents and trust mock_api/category_policies")
    rebuild = f"python generate.py --domain {rep.key} --only tables"
    orders = {o["order_ref"]: o for o in tables.get("orders", [])}
    products = {p["sku"]: p for p in tables.get("products", [])}
    limits = {r["limit"]: r["value"] for r in tables.get("policy_limits", [])}
    authority = {a["approver"]: a["max_refund_inr"] for a in tables.get("refund_authority", [])}

    from datagen.domains.base import as_number as _amount

    def may_approve(approver: str | None, amount: int) -> bool:
        cap = authority.get(approver, 0)
        return approver in authority and (cap is None or amount <= cap)

    fulfilment = tables.get("order_fulfilment")
    if fulfilment and orders and tables.get("delivery_services"):
        services = {(s["service_tier"], s["delivery_zone"]): s["promise_days"]
                    for s in tables["delivery_services"]}
        ladder = tables.get("delay_compensation", [])

        def credit(days: int) -> int:
            return next((r["goodwill_credit_inr"] for r in ladder
                         if days >= r["min_days_late"]
                         and (r["max_days_late"] is None or days <= r["max_days_late"])), 0)

        wrong = []
        for f in fulfilment:
            o = orders[f["order_ref"]]
            placed = datetime.fromisoformat(o["placed_at"]).date()
            ok = (services.get((f["service_tier"], f["delivery_zone"])) == o["delivery_promise_days"]
                  and f["promised_by"] == (placed + timedelta(days=o["delivery_promise_days"])).isoformat())
            if ok and f["delivered_on"]:
                late = max(0, (date.fromisoformat(f["delivered_on"]) - placed).days
                           - o["delivery_promise_days"])
                due = credit(late) if o["status"] == "delivered" else 0
                ok = f["days_late"] == late and f["delay_credit_due_inr"] == due
            if not ok:
                wrong.append(f["order_ref"])
        if wrong:
            rep.fail("shopsense", "order_fulfilment does not follow from the order, the "
                                  f"delivery services and the delay ladder: {_short(wrong)}",
                     rebuild)
        else:
            rep.ok("shopsense", f"all {len(fulfilment)} orders agree with the delivery "
                                f"promise for their service and the delay compensation ladder")

    refunds = tables.get("refunds", [])
    credits = tables.get("goodwill_credits")
    if credits and limits:
        refunded = {r["order_ref"] for r in refunds}
        per_order = [g["order_ref"] for g in credits]
        bad = [g["credit_id"] for g in credits
               if g["amount_inr"] > limits.get("goodwill_cap_per_order_inr", 0)
               or g["order_ref"] in refunded]
        if bad or len(set(per_order)) != len(per_order):
            rep.fail("shopsense", "goodwill credits break the cap, the one-per-order rule or "
                                  f"the no-stacking rule: {_short(bad)}", rebuild)
        else:
            rep.ok("shopsense", f"all {len(credits)} goodwill credits are within the cap, one "
                                f"per order, and never on a refunded order")
    replacements = tables.get("replacements")
    if replacements and authority and orders:
        low = [r["replacement_id"] for r in replacements
               if r["status"] != "requested"
               and not may_approve(r["approved_by"], orders[r["order_ref"]]["order_value_inr"])]
        if low:
            rep.fail("shopsense", "replacements decided below the tier the authority matrix "
                                  f"requires: {_short(low)}", rebuild)
        else:
            rep.ok("shopsense", f"all {len(replacements)} replacements were decided at the "
                                f"tier the refund authority matrix requires")
    tickets = tables.get("support_tickets")
    if tickets and limits and authority:
        refund_by_id = {r["refund_id"]: r for r in refunds}
        alone = [t["ticket_id"] for t in tickets if t["handled_by"] == "auto"
                 and (t["sentiment"] == "angry"
                      or t["contact_number"] >= limits.get("repeat_contact_threshold", 3))]
        low = [t["ticket_id"] for t in tickets
               if t["refund_id"] and t["resolution"] in ("refund_issued", "refund_rejected")
               and not may_approve(t["handled_by"], refund_by_id[t["refund_id"]]["amount_inr"])]
        if alone or low:
            rep.fail("shopsense", "past tickets that break the escalation standard or the "
                                  f"refund authority matrix: {_short(alone + low)}", rebuild)
        else:
            rep.ok("shopsense", f"no past ticket was handled automatically for an angry "
                                f"customer or a repeat contact, and every refund in one was "
                                f"decided at the required tier ({len(tickets)} checked)")

    # Known limits of the default tables, which are kept as v1.0.0 wrote them.
    fresh = "--fresh-table-rng, which makes them agree; the default tables are kept for compatibility"
    if refunds and orders and authority:
        over = sum(r["amount_inr"] > orders[r["order_ref"]]["order_value_inr"] for r in refunds)
        low = sum(r["approved_by"] is not None and r["status"] != "requested"
                  and not may_approve(r["approved_by"], r["amount_inr"]) for r in refunds)
        early = sum(r["requested_on"] < orders[r["order_ref"]]["placed_at"][:10] for r in refunds)
        if over or low or early:
            rep.note("shopsense", f"of {len(refunds)} past refunds, {over} exceed the order "
                                  f"value, {low} were approved below the required tier and "
                                  f"{early} are dated before the order",
                     "refund_authority and refund_rules for what should happen; treat the "
                     "refunds table as history of mixed quality, or generate with "
                     "--fresh-table-rng")
    if orders and products and fulfilment:
        priced = sum(o["order_value_inr"] != products[o["sku"]]["price_inr"] * o["quantity"]
                     for o in orders.values())
        scans = {"placed": ("label_created",), "cancelled": ("cancelled",),
                 "delivered": ("delivered",), "returned": ("returned_to_origin",),
                 "shipped": ("in_transit", "out_for_delivery", "delivery_attempted", "exception")}
        off = sum(s["last_scan"] not in scans[orders[s["order_ref"]]["status"]]
                  for s in tables.get("shipments", []))
        lost_after = limits.get("lost_in_transit_days", 10)
        today = max(o["placed_at"] for o in orders.values())[:10]
        stale = sum(orders[f["order_ref"]]["status"] == "shipped"
                    and (date.fromisoformat(today) - date.fromisoformat(f["promised_by"])).days
                    >= 60 for f in fulfilment)
        if priced or off or stale:
            rep.note("shopsense", f"order value is not price x quantity on {priced} of "
                                  f"{len(orders)} orders, the last shipment scan disagrees "
                                  f"with the order status on {off}, and {stale} shipped orders "
                                  f"are months past their promised date",
                     "orders.order_value_inr as the amount paid, orders.status for where "
                     "the order is, and order_fulfilment for its dates (an undelivered "
                     f"shipped order {lost_after} days past promised_by is lost in "
                     f"transit); or " + fresh)
    policies = {c["category"]: c for c in tables.get("category_policies", [])}
    if policies and products:
        odd = sum(p["warranty_months"] > 0 and not policies[p["category"]]["warranty_eligible"]
                  for p in products.values())
        if odd:
            rep.note("shopsense", f"{odd} products in categories with no warranty show a "
                                  f"warranty period on their listing",
                     "category_policies.warranty_eligible and order_fulfilment.warranty_until, "
                     "as the warranty policy says a listing period in those categories gives "
                     "no cover; or " + fresh)

    if policies and texts:
        silent = []
        for cat, c in policies.items():
            doc = texts.get(c["policy_document"])
            if doc is None:
                continue
            plain = re.sub(r"[*_`\\]", "", doc.lower())
            if c["return_window_days"] is None:
                window = re.search(r"non[- ]?returnable|not returnable|cannot be returned|"
                                   r"no returns", plain)
            else:
                window = re.search(rf"\b{c['return_window_days']}\b[^.\n]{{0,30}}\bdays?\b", plain)
            fee = not c["restocking_fee_pct"] or re.search(
                rf"\b{c['restocking_fee_pct']}\s*(%|per\s?cent)", plain)
            if not window or not fee:
                silent.append(cat)
        if silent:
            rep.warn("shopsense", "category addenda that do not state the return window or "
                                  f"restocking fee in category_policies: {_short(silent)}", regen)
        else:
            rep.ok("shopsense", "every category addendum states the return window and "
                                "restocking fee in category_policies")
    matrix = texts.get("refund-authority")
    if matrix and authority:
        caps = sorted({c for c in authority.values() if c})
        absent = [f"{c:,}" for c in caps if f"{c:,}" not in matrix and str(c) not in matrix]
        if absent:
            rep.warn("shopsense", "refund authorisation matrix does not state the "
                                  f"threshold(s) in refund_authority: {_short(absent)}", regen)
        else:
            rep.ok("shopsense", "refund authorisation matrix states every threshold in "
                                "refund_authority (" + ", ".join(f"{c:,}" for c in caps) + ")")
    shipping = texts.get("shipping-policy")
    if shipping and tables.get("carriers"):
        absent = [c["carrier"] for c in tables["carriers"] if c["carrier"] not in shipping]
        if absent:
            rep.warn("shopsense", f"shipping policy does not name: {_short(absent)}", regen)
        else:
            rep.ok("shopsense", "shipping policy names every carrier in the carriers table")

    if records and orders:
        again = (f"python generate.py --domain {rep.key} --only intake --no-resume   "
                 f"# tickets generated before v1.0.4 invented their order references")
        tagged = [r for r in records if r.get("order_ref")]
        known = [r for r in tagged if r["order_ref"] in orders]
        if tagged and len(known) < 0.9 * len(tagged):
            rep.warn("shopsense", f"{len(tagged) - len(known)} of {len(tagged)} intake tickets "
                                  f"name an order that is not in the orders table", again)
        elif known:
            stray = [r["order_ref"] for r in known
                     if r.get("customer_ref") != orders[r["order_ref"]]["customer_ref"]]
            cap = limits.get("auto_refund_cap_inr", 2_000)
            soft = [r["order_ref"] for r in known
                    if isinstance(r.get("ground_truth"), dict)
                    and (_amount(r["ground_truth"].get("claimed_amount_inr")) or 0) > cap
                    and r["ground_truth"].get("requires_human") is False]
            if stray or soft:
                rep.warn("shopsense", f"intake tickets that disagree with the tables: "
                                      f"{len(stray)} name another customer's order, {len(soft)} "
                                      f"claim more than {cap:,} without requires_human",
                         f"python generate.py --domain {rep.key} --only intake --no-resume")
            else:
                rep.ok("shopsense", f"intake tickets name real orders and their customers, "
                                    f"and every claim above {cap:,} requires a human "
                                    f"({len(known)} checked)")


EXTRAS = {"plantguard": _plantguard, "careflow": _careflow, "lexops": _lexops,
          "wealthpilot": _wealthpilot, "shopsense": _shopsense}


# ------------------------------------------------------------------------ driver
def validate_domain(
    key: str,
    data_root: Path | None = None,
    *,
    stages: tuple[str, ...] = STAGES,
    intake: int | None = None,
    eval_items: int | None = None,
    corpus_docs: int | None = None,
) -> Report:
    rep = Report(key, Path(data_root or settings.output_dir) / key)
    if not rep.path.exists():
        rep.fail("manifest", f"{rep.path} does not exist: nothing has been generated",
                 f"python generate.py --domain {key}")
        return rep
    manifest = check_manifest(rep) if "manifest" in stages else {}
    try:
        manifest = manifest or _load_json(rep.path / "manifest.json")
    except (OSError, ValueError):
        manifest = {}
    seed = manifest.get("seed") if isinstance(manifest.get("seed"), int) else settings.seed
    recorded = (manifest.get("assets") or {}).get("intake") or {}

    texts = check_corpus(rep, corpus_docs) if "corpus" in stages else {}
    records = (
        check_intake(rep, intake or recorded.get("count", 0) + recorded.get("shortfall", 0)
                     or settings.intake_records)
        if "intake" in stages else []
    )
    tables = check_tables(rep, seed) if "tables" in stages else {}
    if "eval" in stages:
        if "corpus" not in stages and (rep.path / "corpus" / "markdown").exists():
            texts = {p.stem: p.read_text("utf-8")
                     for p in (rep.path / "corpus" / "markdown").glob("*.md")}
        check_eval(rep, eval_items or settings.eval_items, texts)
    if key in EXTRAS:
        try:
            # Models escape underscores in markdown (DSCR\_BELOW\_FLOOR).
            plain = {slug: text.replace("\\", "") for slug, text in texts.items()}
            EXTRAS[key](rep, plain, records, tables)
        except (KeyError, TypeError, AttributeError, ValueError, ArithmeticError):
            # Malformed tables are already reported above; the domain checks
            # read those same columns and cannot run until they are fixed.
            rep.warn(key, "domain-specific checks could not run: a table or an intake "
                          "record holds a value of an unexpected kind. Fix any failure "
                          "above, or regenerate the stage it names")
    return rep


def print_report(rep: Report) -> None:
    name = REGISTRY[rep.key].name
    print(f"\n{'=' * 68}\n{name}\n{rep.path}\n{'=' * 68}")
    section = None
    for f in rep.findings:
        if f.section != section:
            section = f.section
            print(f"\n  {section}")
        print(f"    [{f.level}] {f.message}")
        if f.fix:
            print(f"           {'use' if f.level == 'NOTE' else 'fix'}: {f.fix}")
    print(f"\n  {rep.tally()}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m tests.validate_data",
        description="Check that generated data is complete and correctly shaped.",
    )
    p.add_argument("--domain", required=True, choices=sorted(REGISTRY) + ["all"])
    p.add_argument("--data", type=Path, help="Data folder (default: ./data, or DATAGEN_OUTPUT_DIR).")
    p.add_argument("--only", default=",".join(STAGES),
                   help=f"Comma-separated subset of: {', '.join(STAGES)}")
    p.add_argument("--intake", type=int, help="Intake records you asked for (default 200).")
    p.add_argument("--eval-items", type=int, help="Eval cases you asked for (default 20).")
    p.add_argument("--corpus-docs", type=int,
                   help="Corpus documents you asked for, if you capped them.")
    p.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    args = p.parse_args(argv)

    stages = tuple(s.strip() for s in args.only.split(",") if s.strip())
    unknown = set(stages) - set(STAGES)
    if unknown:
        p.error(f"unknown stage(s): {', '.join(sorted(unknown))}")

    keys = sorted(REGISTRY) if args.domain == "all" else [args.domain]
    reports = [
        validate_domain(k, args.data, stages=stages, intake=args.intake,
                        eval_items=args.eval_items, corpus_docs=args.corpus_docs)
        for k in keys
    ]
    for rep in reports:
        print_report(rep)
    fails = sum(r.count("FAIL") for r in reports)
    warns = sum(r.count("WARN") for r in reports)
    notes = sum(r.count("NOTE") for r in reports)
    if len(reports) > 1:
        print(f"\n{'=' * 68}")
        for r in reports:
            verdict = "FAIL" if r.count("FAIL") else "WARN" if r.count("WARN") else "PASS"
            print(f"  [{verdict}] {r.key:12s} {r.tally()}")
    print(f"\n{'=' * 68}")
    if fails:
        print(f"NOT READY: {fails} check(s) failed. Run the fix shown under each one.")
    elif warns:
        print(f"READY, with {warns} warning(s) to read.")
    else:
        print("READY: everything this version generates is present and correct.")
    if notes and not fails:
        print(f"{notes} note(s) describe known limits of the default tables and what to "
              f"use instead.")
    print("=" * 68)
    return 1 if fails or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
