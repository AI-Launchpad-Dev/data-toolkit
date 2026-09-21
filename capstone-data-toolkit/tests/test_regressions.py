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
from datagen.llm import ContentBlocked, LLMError  # noqa: E402
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
        keysets = {
            list(rows[0].keys())[0]: {r[list(rows[0].keys())[0]] for r in rows}
            for rows in tables.values()
            if rows
        }
        broken = []
        for name, rows in tables.items():
            if not rows:
                continue
            pk = list(rows[0].keys())[0]
            for col in rows[0]:
                if col in keysets and col != pk:
                    missing = {r[col] for r in rows} - keysets[col]
                    if missing:
                        broken.append(f"{name}.{col}({len(missing)})")
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
