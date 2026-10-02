"""Regression tests. One test per bug found in the v1.0.0 audit.

Run:  python -m tests.test_regressions
No API key, no network. Should finish in well under a minute.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datagen import llm  # noqa: E402
from datagen.config import settings  # noqa: E402
from datagen.domains import REGISTRY  # noqa: E402
from datagen.llm import ContentBlocked  # noqa: E402
from tests import stub_provider as stub  # noqa: E402

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail and not condition else ""))


def tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="datagen-test-"))


# --------------------------------------------------------------- bug 1
def test_manifest_written() -> None:
    """v1.0.0: write_manifest was only reachable from a dead generate()."""
    print("\nbug 1 -- manifest.json is written by the CLI path")
    import generate as cli

    for key in sorted(REGISTRY):
        out = tmp()
        settings.output_dir = out
        cli.run_domain(key, {"tables"}, dry_run=False)
        mf = out / key / "manifest.json"
        ok = mf.exists()
        detail = ""
        if ok:
            data = json.loads(mf.read_text())
            ok = (
                data.get("contains_real_personal_data") is False
                and data.get("complete") is True
                and len(data.get("public_sources_referenced", [])) > 0
                and "toolkit_version" in data
            )
            detail = "manifest present but fields missing"
        check(f"{key}: manifest.json written and populated", ok, detail)
        shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------- bug 2
def test_intake_terminates() -> None:
    """v1.0.0: empty batches looped forever (2.3M calls in 8s)."""
    print("\nbug 2 -- intake loop terminates on unproductive batches")
    settings.intake_records = 40

    # short_batch deliberately hits the attempt ceiling: one record per call
    # cannot reach the target, so the correct behaviour is to stop, report a
    # shortfall, and not silently spend 200 calls.
    expectations = {
        "empty_batch": {"rows": 0, "shortfall": True},
        "short_batch": {"rows": None, "shortfall": True},
        "happy": {"rows": 40, "shortfall": False},
    }
    for mode, want in expectations.items():
        stub.reset()
        stub.install(mode)
        out = tmp()
        res = REGISTRY["shopsense"]().build_intake(out)
        calls = stub.CALLS["complete_json"]
        bounded = calls <= settings.max_intake_attempts
        rows_ok = want["rows"] is None or res["count"] == want["rows"]
        shortfall_ok = bool(res.get("shortfall")) == want["shortfall"]
        check(
            f"{mode}: bounded at {calls} calls, {res['count']} records, "
            f"shortfall reported={bool(res.get('shortfall'))}",
            bounded and rows_ok and shortfall_ok,
            f"calls={calls} rows={res['count']}",
        )
        shutil.rmtree(out, ignore_errors=True)


def test_record_ids_sequential() -> None:
    """v1.0.0: len(rows)+i double-counted, so IDs skipped every other integer."""
    print("\nbug 7 -- record_id is dense and sequential")
    stub.reset()
    stub.install("happy")
    settings.intake_records = 40
    out = tmp()
    REGISTRY["careflow"]().build_intake(out)
    rows = [
        json.loads(x)
        for x in (out / "intake" / "records.jsonl").read_text().splitlines()
    ]
    ids = [r["record_id"] for r in rows]
    expected = [f"CAREFLOW-{i:05d}" for i in range(len(rows))]
    check("record_ids are 0..n-1 with no gaps", ids == expected, f"got {ids[:4]}")
    shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------- bug 3
def test_safety_block_handled() -> None:
    """v1.0.0: a blocked prompt raised an uncaught KeyError('candidates')."""
    print("\nbug 3 -- provider safety blocks raise ContentBlocked, not KeyError")
    stub.uninstall()  # these assertions target the real provider layer
    settings.gemini_api_key = "test"
    settings.provider = "gemini"
    settings.max_retries = 2

    payloads = {
        "no candidates": {"promptFeedback": {"blockReason": "SAFETY"}},
        "empty candidate list": {"candidates": []},
        "finishReason SAFETY": {
            "candidates": [{"finishReason": "SAFETY", "content": {}}]
        },
    }
    for name, payload in payloads.items():
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda p=payload: p
        with patch.object(requests, "post", return_value=resp):
            try:
                llm.complete("hi")
                check(f"{name}: raises ContentBlocked", False, "no exception raised")
            except ContentBlocked:
                check(f"{name}: raises ContentBlocked", True)
            except Exception as exc:  # noqa: BLE001
                check(
                    f"{name}: raises ContentBlocked",
                    False,
                    f"got {type(exc).__name__}",
                )


def test_blocked_doc_skipped_not_fatal() -> None:
    """One refused document must not destroy a 50-document run."""
    print("\nbug 3b -- a single blocked document is skipped and reported")
    stub.reset()
    stub.install("happy", block_slugs=("escalation",))
    settings.corpus_docs = 100
    out = tmp()
    res = REGISTRY["careflow"]().build_corpus(out)
    check(
        "run continues past a blocked document",
        res["count"] > 0 and res.get("blocked"),
        f"count={res['count']} blocked={res.get('blocked')}",
    )
    shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------- bug 4
def test_corpus_docs_cap() -> None:
    """v1.0.0: --corpus-docs 4 generated all 19 documents."""
    print("\nbug 4 -- --corpus-docs actually caps generation")
    for cap in (3, 5):
        stub.reset()
        stub.install("happy")
        settings.corpus_docs = cap
        out = tmp()
        res = REGISTRY["lexops"]().build_corpus(out)
        made = stub.CALLS["complete"]
        check(
            f"cap={cap}: {made} LLM calls, {res['count']} docs",
            made == cap and res["count"] == cap,
        )
        shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------- bug 5
def test_resume() -> None:
    """v1.0.0: a crashed run regenerated everything from scratch."""
    print("\nbug 5 -- completed documents are skipped on re-run")
    settings.corpus_docs = 6
    settings.resume = True
    out = tmp()

    stub.reset()
    stub.install("happy")
    REGISTRY["careflow"]().build_corpus(out)
    first = stub.CALLS["complete"]

    stub.reset()
    stub.install("happy")
    res = REGISTRY["careflow"]().build_corpus(out)
    second = stub.CALLS["complete"]
    check(
        f"re-run costs 0 calls (first={first}, second={second})",
        second == 0 and res.get("resumed") == first,
    )

    stub.reset()
    stub.install("happy")
    settings.resume = False
    REGISTRY["careflow"]().build_corpus(out)
    check("--no-resume forces regeneration", stub.CALLS["complete"] == first)
    settings.resume = True
    shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------- bug 6
def test_tables_built_once() -> None:
    """v1.0.0: seed_tables() ran twice per invocation, once just to print names."""
    print("\nbug 6 -- seed tables are built once per run")
    spec = REGISTRY["plantguard"]()
    calls = {"n": 0}
    original = spec.seed_tables

    def counted():
        calls["n"] += 1
        return original()

    spec.seed_tables = counted  # type: ignore[method-assign]
    out = tmp()
    spec.build_seed_tables(out)
    spec.build_seed_tables(out)
    expected = 2 if settings.legacy_table_rng else 1
    check(
        f"cached across calls ({calls['n']} builds, legacy_rng={settings.legacy_table_rng})",
        calls["n"] == expected,
    )
    shutil.rmtree(out, ignore_errors=True)


def test_table_names_declared_match_built() -> None:
    """table_names is displayed without building; it must not drift."""
    print("\nbug 6b -- declared table_names match what is actually built")
    for key, cls in sorted(REGISTRY.items()):
        spec = cls()
        built = tuple(spec.seed_tables().keys())
        check(f"{key}: declared names match built", spec.table_names == built,
              f"declared={spec.table_names} built={built}")


# --------------------------------------------------------------- bug 10
def test_eval_distribution_warning() -> None:
    """v1.0.0: the guide promised a category mix nothing enforced."""
    print("\nbug 10 -- skewed eval sets are flagged")
    settings.eval_items = 20

    stub.reset()
    stub.install("all_factual")
    out = tmp()
    res = REGISTRY["shopsense"]().build_eval_set(out, ["Doc A"])
    check("all-factual eval set produces warnings", bool(res.get("distribution_warnings")))
    shutil.rmtree(out, ignore_errors=True)

    stub.reset()
    stub.install("happy")
    out = tmp()
    res = REGISTRY["shopsense"]().build_eval_set(out, ["Doc A"])
    check("balanced eval set produces none", not res.get("distribution_warnings"),
          str(res.get("distribution_warnings")))
    shutil.rmtree(out, ignore_errors=True)


# ------------------------------------------------------- standing invariants
def test_foreign_keys() -> None:
    print("\ninvariant -- referential integrity across mock API tables")
    for key, cls in sorted(REGISTRY.items()):
        tables = cls().seed_tables()
        # A table owns a key only if its first column is unique. Tables with
        # a composite key (telemetry, technician_calendar) start with a
        # repeating column and must not be mistaken for the owner.
        keysets = {}
        for rows in tables.values():
            if not rows:
                continue
            first = list(rows[0].keys())[0]
            values = [r[first] for r in rows]
            if len(set(values)) == len(values):
                keysets[first] = set(values)
        broken = []
        for name, rows in tables.items():
            if not rows:
                continue
            pk = list(rows[0].keys())[0]
            for col in rows[0]:
                if col in keysets and col != pk:
                    # None is a legitimately empty optional reference.
                    missing = {r[col] for r in rows if r[col] is not None} - keysets[col]
                    if missing:
                        broken.append(f"{name}.{col}({len(missing)})")
        # References whose column name differs from the key it points at.
        for source, target in cls.references.items():
            (st, sc), (tt, tc) = source.split("."), target.split(".")
            known = {r[tc] for r in tables[tt]}
            missing = {r[sc] for r in tables[st] if r[sc] is not None} - known
            if missing:
                broken.append(f"{source}({len(missing)})")
        check(f"{key}: no dangling references", not broken, ", ".join(broken))


def test_reproducible() -> None:
    print("\ninvariant -- same seed produces identical tables")
    for key in sorted(REGISTRY):
        a = REGISTRY[key]().seed_tables()
        b = REGISTRY[key]().seed_tables()
        check(f"{key}: deterministic", json.dumps(a, default=str) == json.dumps(b, default=str))


def test_no_dead_code() -> None:
    print("\ninvariant -- removed APIs stay removed")
    import datagen.writers as writers

    check("writers.checksum removed", not hasattr(writers, "checksum"))
    check("DomainSpec.generate removed", not hasattr(REGISTRY["careflow"], "generate"))
    check("settings.concurrency removed", not hasattr(settings, "concurrency"))


# ------------------------------------------------------------ v1.0.3 checks
def test_dependency_preflight() -> None:
    """v1.0.2: a half-installed venv died with a 12-line pydantic traceback."""
    print("\nv1.0.3 -- broken dependencies produce a repair command")
    import importlib

    import generate as cli

    real = importlib.import_module

    def missing_core(name, *a, **k):
        if name == "pydantic_core":
            raise ModuleNotFoundError("No module named 'pydantic_core'")
        return real(name, *a, **k)

    message = ""
    with patch.object(importlib, "import_module", missing_core):
        try:
            cli.check_dependencies()
        except SystemExit as exc:
            message = str(exc)
    check(
        "names the package and the fix",
        "pydantic-core" in message and "python -m pip install" in message,
        message[:120],
    )
    try:
        cli.check_dependencies()
        check("silent when everything imports", True)
    except SystemExit:
        check("silent when everything imports", False)


def test_plantguard_operations_tables() -> None:
    """v1.0.2: technician_id pointed at nothing; criticality had no factors."""
    print("\nv1.0.3 -- PlantGuard operations tables are present and coherent")
    spec = REGISTRY["plantguard"]()
    t = spec.seed_tables()

    # Adding tables must not move a single value in the original four.
    bare = REGISTRY["plantguard"]()
    bare._operations_tables = lambda *a, **k: {}  # type: ignore[method-assign]
    original = bare.seed_tables()
    check(
        "original four tables unchanged by the new ones",
        all(json.dumps(t[k], default=str) == json.dumps(original[k], default=str)
            for k in ("assets", "telemetry", "work_orders", "inventory")),
    )

    tech = {r["technician_id"]: r for r in t["technicians"]}
    check("every work order's technician exists",
          all(w["technician_id"] in tech for w in t["work_orders"]))

    safety = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    env = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
    cls = {"A": 0, "B": 1, "C": 2}

    def cost_level(rate: int) -> int:
        return 0 if rate >= 30_000 else 1 if rate >= 10_000 else 2

    assets = {a["asset_tag"]: a for a in t["assets"]}
    check(
        "criticality equals the most severe of its three factors",
        all(
            min(safety[r["safety_risk"]], env[r["environmental_impact"]],
                cost_level(r["downtime_cost_per_hour_inr"])) == cls[r["criticality"]]
            and assets[r["asset_tag"]]["criticality"] == r["criticality"]
            for r in t["asset_criticality"]
        ) and len(t["asset_criticality"]) == len(assets),
    )

    wo = {w["work_order_id"]: w for w in t["work_orders"]}
    cal = {(c["technician_id"], c["date"]): c for c in t["technician_calendar"]}
    booked: dict[tuple[str, str], float] = {}
    ok_skill = ok_slot = ok_permit = True
    for d in t["work_order_details"]:
        w = wo[d["work_order_id"]]
        who = tech[w["technician_id"]]
        ok_skill &= d["required_skill"] in (who["primary_skill"], who["secondary_skill"])
        ok_permit &= (d["permit_type"] is not None) == w["permit_required"] and (
            d["permit_type"] is None or who[f"{d['permit_type']}_certified"]
        )
        if d["scheduled_date"]:
            key = (w["technician_id"], d["scheduled_date"])
            ok_slot &= w["status"] != "closed" and cal[key]["status"] == "on_shift"
            booked[key] = booked.get(key, 0) + d["estimated_hours"]
    check("work orders need a skill their technician holds", ok_skill)
    check("permit work goes to a technician certified for it", ok_permit)
    check("work is scheduled only on a rostered shift", ok_slot)
    check(
        "calendar booked hours match the schedule, with no overbooking",
        all(c["booked_hours"] == booked.get(k, 0) and c["available_hours"] >= 0
            for k, c in cal.items()),
    )
    check(
        "no purchase order above the automatic limit is auto-raised",
        not any(p["raised_by"] == "auto_reorder" and p["total_inr"] > 200_000
                for p in t["purchase_orders"]),
    )
    inv = {i["part_number"]: i for i in t["inventory"]}
    sup = {x["supplier_id"]: x for x in t["suppliers"]}
    check(
        "each part's supplier is in the tier the inventory records",
        all(sup[p["supplier_id"]]["tier"] == inv[p["part_number"]]["supplier_tier"]
            for p in t["part_suppliers"]),
    )


def test_manuals_cite_real_parts() -> None:
    """v1.0.2: manuals were told to invent part numbers the ERP did not hold."""
    print("\nv1.0.3 -- equipment manuals are given real inventory part numbers")
    spec = REGISTRY["plantguard"]()
    parts = {p["part_number"] for p in spec.cached_seed_tables()["inventory"]}
    import re

    cited: set[str] = set()
    for doc in spec.doc_specs():
        if doc.slug.startswith("manual-"):
            cited |= set(re.findall(r"VPW-P-\d{5}", spec.corpus_instruction(doc)))
    check("manual prompts carry part numbers", len(cited) >= 8, f"{len(cited)} cited")
    check("every cited part exists in inventory", cited <= parts)


def test_docs_cover_schema() -> None:
    """A table nobody documented is a table nobody finds until M6."""
    print("\nv1.0.3 -- README documents every table, and every PlantGuard column")
    import generate as cli

    root = Path(__file__).resolve().parents[2] / "README.md"
    text = (root.read_text("utf-8") if root.exists() else "") + (
        Path(__file__).resolve().parents[1] / "README.md"
    ).read_text("utf-8")
    for key in sorted(REGISTRY):
        schema = cli.table_schema(key)
        missing = [name for name in schema if f"`{name}`" not in text]
        check(f"{key}: every table named in the README", not missing, ", ".join(missing))
        rows = f"{sum(i['rows'] for i in schema.values()):,}"  # type: ignore[misc]
        ncols = sum(len(i["columns"]) for i in schema.values())  # type: ignore[arg-type]
        check(f"{key}: README states {len(schema)} tables, {ncols} columns, {rows} rows",
              f"| {len(schema)} | {ncols} | {rows} |" in text)
    cols = {
        c for info in cli.table_schema("plantguard").values()
        for c in info["columns"]  # type: ignore[union-attr]
    }
    missing = sorted(c for c in cols if f"`{c}`" not in text)
    check("plantguard: every column named in the README", not missing, ", ".join(missing))


def test_intake_fields_declared() -> None:
    """The validator checks records against fields each domain declares."""
    print("\nv1.0.3 -- declared intake fields match what the prompt asks for")
    for key, cls in sorted(REGISTRY.items()):
        spec = cls()
        prompt = spec.intake_prompt(20)
        wanted = spec.intake_fields + spec.intake_truth_fields + ("ground_truth",)
        missing = [f for f in wanted if f'"{f}"' not in prompt]
        check(f"{key}: {len(wanted) - 1} declared fields all appear in the prompt",
              bool(spec.intake_fields) and not missing, ", ".join(missing))


def test_validator() -> None:
    """A generated dataset validates; a damaged one is reported precisely."""
    print("\nv1.0.3 -- tests.validate_data accepts good data and catches damage")
    import generate as cli
    from tests import validate_data as vd

    saved = (settings.output_dir, settings.corpus_docs, settings.intake_records,
             settings.eval_items)
    out = tmp()
    settings.output_dir, settings.corpus_docs = out, 50
    settings.intake_records, settings.eval_items = 40, 20
    stub.reset()
    stub.install("happy")
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        for key in sorted(REGISTRY):
            cli.run_domain(key, {"corpus", "intake", "tables", "eval"}, dry_run=False)
        # A later tables-only run must not erase the record of the rest.
        cli.run_domain("plantguard", {"tables"}, dry_run=False)
    recorded = json.loads((out / "plantguard" / "manifest.json").read_text())["assets"]
    check("manifest still lists all four assets after a tables-only re-run",
          {"corpus", "intake", "mock_api", "eval"} <= set(recorded), str(sorted(recorded)))

    for key in sorted(REGISTRY):
        rep = vd.validate_domain(key, out)
        failed = [f.message for f in rep.findings if f.level == "FAIL"]
        check(f"{key}: freshly generated data has no failures "
              f"({rep.count('PASS')} checks pass)", not failed, "; ".join(failed)[:160])

    pg = out / "plantguard"
    (pg / "corpus" / "pdf" / "manual-chiller.pdf").unlink()
    (pg / "mock_api" / "technicians.json").unlink()
    rows = json.loads((pg / "mock_api" / "asset_criticality.json").read_text())
    for row in rows:
        del row["downtime_cost_per_hour_inr"]
    (pg / "mock_api" / "asset_criticality.json").write_text(json.dumps(rows))
    orders = json.loads((pg / "mock_api" / "work_orders.json").read_text())
    orders[0]["asset_tag"] = "VPW-NOPE-99"
    (pg / "mock_api" / "work_orders.json").write_text(json.dumps(orders))
    cases = json.loads((pg / "eval" / "golden_set.json").read_text())
    (pg / "eval" / "golden_set.json").write_text(
        json.dumps([c for c in cases if c["id"] != "PLANTGUARD-EV-902"]))
    (pg / "intake" / "records.jsonl").unlink()

    rep = vd.validate_domain("plantguard", out)
    for label, text in [
        ("a missing PDF", "manual-chiller"),
        ("a missing table", "missing: technicians"),
        ("a dropped column", "missing downtime_cost_per_hour_inr"),
        ("a dangling reference", "work_orders.asset_tag"),
        ("a missing hand-written eval case", "PLANTGUARD-EV-902"),
        ("missing intake records", "records.jsonl is missing"),
    ]:
        check(f"damaged data: reports {label}", rep.has("FAIL", text))
    with contextlib.redirect_stdout(io.StringIO()):
        status = vd.main(["--domain", "plantguard", "--data", str(out), "--only", "tables"])
    check("damaged data: exit status is non-zero", status == 1)
    check("nothing generated: says so instead of crashing",
          vd.validate_domain("lexops", out / "nowhere").has("FAIL", "does not exist"))

    (settings.output_dir, settings.corpus_docs, settings.intake_records,
     settings.eval_items) = saved
    shutil.rmtree(out, ignore_errors=True)


# ------------------------------------------------------------ v1.0.4 checks
_ORIGINAL = {"careflow": 4, "lexops": 3, "wealthpilot": 4, "shopsense": 5}


def test_new_tables_leave_originals_alone() -> None:
    """v1.0.4 added 41 tables to four domains. Teams already built on the
    original ones, so not one value in them may move."""
    print("\nv1.0.4 -- new tables do not change the original ones")
    for key, count in _ORIGINAL.items():
        full = REGISTRY[key]().seed_tables()
        bare = REGISTRY[key]()
        bare._extension_tables = lambda *a, **k: {}  # type: ignore[attr-defined]
        original = bare.seed_tables()
        names = list(REGISTRY[key].table_names)[:count]
        check(
            f"{key}: {count} original tables unchanged by {len(full) - count} new ones",
            list(original) == names
            and all(json.dumps(full[n], default=str) == json.dumps(original[n], default=str)
                    for n in names),
        )


def test_documents_tables_and_labels_agree() -> None:
    """v1.0.3: a restocking fee, a co-pay or a DSCR floor existed only as
    prose the model invented, and no table agreed with it."""
    print("\nv1.0.4 -- documents, tables and labels state the same facts")
    from tests import validate_data as vd

    for key in _ORIGINAL:
        # The document prompts must carry the figures the tables hold. The
        # validator's own cross-checks are run against the prompts, which is
        # the most a test can do without a model.
        spec = REGISTRY[key]()
        prompts = {d.slug: spec.corpus_instruction(d) for d in spec.doc_specs()}
        rep = vd.Report(key, Path("."))
        vd.EXTRAS[key](rep, prompts, [], spec.cached_seed_tables())
        bad = [f.message for f in rep.findings if f.level in ("WARN", "FAIL")]
        check(f"{key}: document prompts carry the figures in the tables, and the new "
              f"tables obey the policy", not bad, "; ".join(bad)[:200])

    # With --fresh-table-rng the original tables are reconciled too, so none
    # of the known limits the validator notes in default mode remain.
    legacy = settings.legacy_table_rng
    settings.legacy_table_rng = False
    try:
        for key in _ORIGINAL:
            spec = REGISTRY[key]()
            rep = vd.Report(key, Path("."))
            vd.EXTRAS[key](rep, {}, [], spec.cached_seed_tables())
            left = [f.message for f in rep.findings if f.level != "PASS"]
            check(f"{key}: --fresh-table-rng leaves no contradiction between tables",
                  not left, "; ".join(left)[:200])
    finally:
        settings.legacy_table_rng = legacy

    cases = {c.id: c.expected for key in _ORIGINAL
             for c in REGISTRY[key]().handwritten_eval_cases()}
    check("hand-written eval answers are computed from the shared facts",
          "1,480" in cases["CAREFLOW-EV-906"] and "9,676" in cases["SHOPSENSE-EV-906"]
          and "13.00 percent" in cases["WEALTHPILOT-EV-910"]
          and "a score of 40" in cases["LEXOPS-EV-901"])


def test_new_tables_obey_their_own_policy() -> None:
    """Found in review of v1.0.4 before release: tables added to remove
    contradictions carried some of their own."""
    print("\nv1.0.4 -- the new tables obey the policy they sit beside")
    from datetime import datetime, timedelta

    t = REGISTRY["wealthpilot"]().cached_seed_tables()
    spec = REGISTRY["wealthpilot"]()
    ref = {r["application_id"]: r for r in t["underwriting_reference"]}
    grade = {g["grade"]: g for g in t["risk_grades"]}
    sector = {s["sector"]: s for s in t["sector_policies"]}
    applicant = {a["applicant_id"]: a for a in t["applicants"]}
    wrong, loose = [], []
    for app in t["loan_applications"]:
        r = ref[app["application_id"]]
        truth = spec.finalize_intake_record({"application_id": app["application_id"]})["ground_truth"]
        if truth["missing_fields"]:
            if not truth["requires_human_signoff"] or truth["risk_band"] == "approve":
                wrong.append(app["application_id"])
        elif (truth["risk_band"], truth["requires_human_signoff"], truth["dscr"]) != (
            r["risk_band"], r["requires_human_signoff"], r["dscr"]
        ):
            wrong.append(app["application_id"])
        if r["risk_band"] == "approve":
            g = grade[r["internal_grade"]]
            limit = min(g["max_tenor_months"], sector[applicant[app["applicant_id"]]["sector"]]["max_tenor_months"])
            if (app["requested_tenor_months"] > limit
                    or app["collateral_value_inr"] < app["requested_amount_inr"] * g["collateral_cover_pct"] / 100):
                loose.append(app["application_id"])
    check("wealthpilot: intake labels equal underwriting_reference; an incomplete "
          "application is never approvable", not wrong, ", ".join(wrong[:5]))
    check("wealthpilot: nothing is approvable beyond the grade's tenor or below its "
          "collateral cover", not loose, ", ".join(loose[:5]))

    t = REGISTRY["lexops"]().cached_seed_tables()
    stands = {(c["contract_id"], c["clause_type"]): c["position"] for c in t["contract_clauses"]}
    effective = {c["contract_id"]: c for c in t["contracts"]}
    off = [n["negotiation_id"] for n in t["negotiation_history"] if n["contract_id"] and (
        n["agreed_position"] != stands[(n["contract_id"], n["clause_type"])]
        or (effective[n["contract_id"]]["status"] in ("executed", "expired")
            and n["occurred_on"] >= effective[n["contract_id"]]["effective_date"]))]
    check("lexops: a negotiation ends where the contract's clause stands, before the "
          "contract took effect", not off, ", ".join(off[:5]))

    t = REGISTRY["careflow"]().cached_seed_tables()
    site = {s["site_id"]: s for s in t["sites"]}
    bad, by_provider = [], {}
    for slot in t["appointment_slots"]:
        start = datetime.fromisoformat(slot["starts_at"])
        end = start + timedelta(minutes=slot["duration_minutes"])
        s_ = site[slot["site_id"]]
        if (start.strftime("%H:%M") < s_["opens_at"] or end.strftime("%H:%M") > s_["closes_at"]
                or (slot["mode"] == "telehealth" and not s_["telehealth_enabled"])):
            bad.append(slot["slot_id"])
        by_provider.setdefault(slot["provider_id"], []).append((start, end))
    for spans in by_provider.values():
        spans.sort()
        bad += ["overlap" for a, b in zip(spans, spans[1:]) if a[1] > b[0]]
    raised = {r["referral_id"]: r for r in t["referrals"]}
    stray = [i["interaction_id"] for i in t["patient_interactions"] if i["topic"] == "referral_status"
             and (i["referral_id"] not in raised
                  or raised[i["referral_id"]]["patient_ref"] != i["patient_ref"]
                  or i["occurred_at"][:10] < raised[i["referral_id"]]["raised_on"])]
    check("careflow: slots sit inside site hours, never overlap, and telehealth only "
          "where the site offers it", not bad, ", ".join(bad[:5]))
    check("careflow: a referral-status contact is about that patient's referral, after "
          "it was raised", not stray, ", ".join(stray[:5]))

    spec = REGISTRY["shopsense"]()
    t = spec.cached_seed_tables()
    order = {o["order_ref"]: o for o in t["orders"]}
    kept = all(order[g["order_ref"]]["status"] == "delivered" for g in t["goodwill_credits"])
    joined = {c["customer_ref"]: c["joined_on"] for c in t["customers"]}
    early = [x["ticket_id"] for x in t["support_tickets"]
             if x["order_ref"] is None and x["opened_at"][:10] < joined[x["customer_ref"]]]
    check("shopsense: goodwill only on orders the customer kept; no ticket before the "
          "account existed", kept and not early, ", ".join(early[:5]))
    big = next(o for o in t["orders"] if o["order_value_inr"] > 2_000)
    labels = [spec.finalize_intake_record({"order_ref": big["order_ref"], "ground_truth": g})
              ["ground_truth"] for g in (
        {"intent": "refund_request", "claimed_amount_inr": "34,000"},
        {"intent": "refund_request", "claimed_amount_inr": None, "escalation_triggers": None},
        {"intent": "track_order", "claimed_amount_inr": None, "escalation_triggers": "x"},
    )]
    survived = spec.finalize_intake_record({"order_ref": ["x"], "customer_ref": {"a": 1},
                                            "ground_truth": {"claimed_amount_inr": True}})
    check("shopsense: triggers are computed whatever shape the model's fields take",
          [g["requires_human"] for g in labels] == [True, True, False]
          and labels[0]["claimed_amount_inr"] == 34_000
          and survived["ground_truth"]["requires_human"] is False)

    # A resumed run does not write a second record about an order already used.
    spec = REGISTRY["shopsense"]()
    first = [o["order_ref"] for o in spec.intake_sample(t["orders"], 20)]
    resumed = REGISTRY["shopsense"]()
    resumed._intake_used = set(first[:15])  # 15 of the 20 came back before the crash
    again = [o["order_ref"] for o in resumed.intake_sample(resumed.cached_seed_tables()["orders"], 20)]
    check("intake sampling skips rows already written about, across a resume",
          not set(again) & set(first[:15]) and again[:5] == first[15:], str(again[:6]))


def test_intake_uses_real_ids() -> None:
    """v1.0.3: the model invented patient, applicant and order references,
    so no tool could look up the subject of an intake record."""
    print("\nv1.0.4 -- intake records are written about real rows")
    import re

    keyed = {"careflow": ("patients", "patient_ref"), "lexops": ("counterparties", "counterparty_id"),
             "wealthpilot": ("loan_applications", "application_id"), "shopsense": ("orders", "order_ref")}
    for key, (table, column) in keyed.items():
        spec = REGISTRY[key]()
        known = {r[column] for r in spec.cached_seed_tables()[table]}
        listed: list[str] = []
        for _ in range(5):
            prompt = spec.intake_prompt(20)
            roster = prompt[prompt.rindex(":\n") :]
            listed += [m for m in re.findall(r"^  (\S+) \|", roster, flags=re.M)]
        check(f"{key}: 5 batches list 100 different rows of {table}, all real",
              len(listed) == 100 and set(listed) <= known
              and len(set(listed)) == min(100, len(known)),
              f"{len(listed)} listed, {len(set(listed))} distinct")

    spec = REGISTRY["shopsense"]()
    tables = spec.cached_seed_tables()
    order = next(o for o in tables["orders"] if o["order_value_inr"] > 2_000)
    record = spec.finalize_intake_record({
        "order_ref": order["order_ref"], "customer_ref": "KW-C-99999", "received_at": "x",
        "ground_truth": {"intent": "refund_request", "category": "?", "sentiment": "calm",
                         "claimed_amount_inr": order["order_value_inr"],
                         "escalation_triggers": ["made_up"], "requires_human": False},
    })
    truth = record["ground_truth"]
    check("shopsense: customer, timestamp, category and triggers are set from the tables",
          record["customer_ref"] == order["customer_ref"]
          and record["received_at"] >= order["placed_at"]
          and truth["category"] in {p["category"] for p in tables["products"]}
          and "refund_above_auto_cap" in truth["escalation_triggers"]
          and "made_up" not in truth["escalation_triggers"] and truth["requires_human"] is True)

    spec = REGISTRY["wealthpilot"]()
    tables = spec.cached_seed_tables()
    app = tables["loan_applications"][0]
    ref = next(r for r in tables["underwriting_reference"]
               if r["application_id"] == app["application_id"])
    record = spec.finalize_intake_record({
        "application_id": app["application_id"],
        "ground_truth": {"dscr": 99.0, "risk_band": "approve"},
    })
    check("wealthpilot: the DSCR label is computed, not the model's arithmetic",
          record["ground_truth"]["dscr"] != 99.0
          and record["requested_amount_inr"] == app["requested_amount_inr"]
          and (record["ground_truth"]["missing_fields"]
               or abs(record["ground_truth"]["dscr"] - ref["dscr"]) < 0.011))


def test_eval_grounding() -> None:
    """v1.0.3: eval cases were written from document titles alone, so the
    'expected' answers quoted figures that were in no document."""
    print("\nv1.0.4 -- eval answers are checked against the corpus")
    from datagen.grounding import canonical_title, is_grounded

    doc = "Clause 4.2: the return window for Electronics is 15 days. Fee: 15% of the price."
    check("an answer whose figures are in the cited document is grounded",
          is_grounded("Electronics can be returned within 15 days.", [doc]) is True)
    check("an answer with figures the document does not contain is not",
          is_grounded("Returns are accepted for 45 days with a 250 rupee fee.", [doc]) is False)
    check("an answer with no figures is left to the grader",
          is_grounded("Escalate to a human and do not admit liability.", [doc]) is None)
    check("a slightly misquoted title is repaired to the real one",
          canonical_title("Kartway Returns & Refunds Policy",
                          ["Kartway Returns and Refunds Policy", "Shipping Policy"])
          == "Kartway Returns and Refunds Policy")

    stub.reset()
    stub.install("happy")
    out = tmp()
    spec = REGISTRY["shopsense"]()
    (out / "corpus" / "markdown").mkdir(parents=True)
    for d in spec.doc_specs():
        (out / "corpus" / "markdown" / f"{d.slug}.md").write_text(f"# {d.title}\n\n{doc}", "utf-8")
    res = spec.build_eval_set(out, [d.title for d in spec.doc_specs()])
    check("the eval stage reads the corpus and reports that it did",
          res.get("grounded_in_corpus") is True, str({k: res.get(k) for k in
                                                       ("grounded_in_corpus", "count")}))
    shutil.rmtree(out, ignore_errors=True)
    stub.uninstall()


def main() -> int:
    print("=" * 68)
    print("Capstone Data Toolkit -- regression suite (offline, no API key)")
    print("=" * 68)

    settings.output_dir = Path(tempfile.gettempdir())
    for fn in (
        test_manifest_written,
        test_intake_terminates,
        test_record_ids_sequential,
        test_safety_block_handled,
        test_blocked_doc_skipped_not_fatal,
        test_corpus_docs_cap,
        test_resume,
        test_tables_built_once,
        test_table_names_declared_match_built,
        test_eval_distribution_warning,
        test_foreign_keys,
        test_reproducible,
        test_no_dead_code,
        test_dependency_preflight,
        test_plantguard_operations_tables,
        test_manuals_cite_real_parts,
        test_docs_cover_schema,
        test_intake_fields_declared,
        test_validator,
        test_new_tables_leave_originals_alone,
        test_documents_tables_and_labels_agree,
        test_new_tables_obey_their_own_policy,
        test_intake_uses_real_ids,
        test_eval_grounding,
    ):
        fn()

    print("\n" + "=" * 68)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
    print("=" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
