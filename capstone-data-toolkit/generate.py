#!/usr/bin/env python3
"""Capstone data generator CLI.

Examples
--------
    # See what would be produced without spending a single API call
    python generate.py --domain shopsense --dry-run

    # Generate everything for one capstone
    python generate.py --domain careflow

    # Just the parts you need right now
    python generate.py --domain lexops --only corpus,eval

    # Mock API tables only -- no LLM, no API key, runs offline in seconds
    python generate.py --domain plantguard --only tables

    # Smaller corpus while you iterate
    python generate.py --domain wealthpilot --corpus-docs 8 --intake 20

    # A crashed run picks up where it stopped; --no-resume forces a rebuild
    python generate.py --domain careflow --no-resume
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from datagen import __version__
from datagen.config import settings
from datagen.domains import REGISTRY
from datagen.llm import LLMError
from datagen.writers import write_manifest

_STAGES = ("corpus", "intake", "tables", "eval")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="generate.py",
        description="Generate capstone datasets for the Applied AI programme.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--domain",
        required=True,
        choices=sorted(REGISTRY) + ["all"],
        help="Which capstone to generate data for.",
    )
    p.add_argument(
        "--only",
        default=",".join(_STAGES),
        help=f"Comma-separated subset of stages: {', '.join(_STAGES)}",
    )
    p.add_argument("--seed", type=int, help="Override the reproducibility seed.")
    p.add_argument("--corpus-docs", type=int, help="Cap on corpus documents.")
    p.add_argument("--intake", type=int, help="Number of intake records.")
    p.add_argument("--eval-items", type=int, help="Size of the golden eval set.")
    p.add_argument("--provider", choices=("gemini", "openrouter", "ollama"))
    p.add_argument("--out", type=Path, help="Output directory.")
    p.add_argument(
        "--no-resume",
        action="store_true",
        help="Regenerate corpus documents even if the files already exist.",
    )
    p.add_argument(
        "--fresh-table-rng",
        action="store_true",
        help="Build mock API tables from a single clean RNG draw. Changes table "
        "contents relative to v1.0.0 -- use on new projects only.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generation plan and exit without calling any API.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def apply_overrides(args: argparse.Namespace) -> None:
    if args.seed is not None:
        settings.seed = args.seed
    if args.corpus_docs is not None:
        settings.corpus_docs = args.corpus_docs
    if args.intake is not None:
        settings.intake_records = args.intake
    if args.eval_items is not None:
        settings.eval_items = args.eval_items
    if args.provider:
        settings.provider = args.provider
    if args.out:
        settings.output_dir = args.out
    if args.no_resume:
        settings.resume = False
    if args.fresh_table_rng:
        settings.legacy_table_rng = False


def preflight(stages: set[str]) -> None:
    """Fail fast on a missing key rather than 40 documents in."""
    if not (stages & {"corpus", "intake", "eval"}):
        return  # tables-only needs no provider
    if settings.provider == "gemini" and not settings.gemini_api_key:
        sys.exit(
            "No Gemini key. Set DATAGEN_GEMINI_API_KEY in .env, or run with\n"
            "  --provider ollama   (local, no key)\n"
            "  --only tables       (no LLM needed)"
        )
    if settings.provider == "openrouter" and not settings.openrouter_api_key:
        sys.exit("No OpenRouter key. Set DATAGEN_OPENROUTER_API_KEY in .env.")


def model_name() -> str:
    return {
        "gemini": settings.gemini_model,
        "openrouter": settings.openrouter_model,
        "ollama": settings.ollama_model,
    }[settings.provider]


def run_domain(key: str, stages: set[str], dry_run: bool) -> None:
    spec = REGISTRY[key]()
    docs = spec.planned_docs()

    print(f"\n{'=' * 68}\n{spec.name}\n{'=' * 68}")
    print(f"  provider   : {settings.provider} ({model_name()})")
    print(f"  seed       : {settings.seed}")
    print(f"  stages     : {', '.join(sorted(stages))}")
    print(f"  corpus     : {len(docs)} documents (markdown + PDF)")
    print(f"  intake     : {settings.intake_records} records")
    print(f"  eval       : {settings.eval_items} cases")
    # Declared, not built -- printing table names must not cost 20,000 rows.
    print(f"  tables     : {', '.join(spec.table_names)}")
    print("\n  public datasets this domain is grounded against:")
    for src in spec.public_sources:
        print(f"    - {src['name']}  [{src['licence']}]")

    if dry_run:
        approx_calls = (
            (len(docs) if "corpus" in stages else 0)
            + (-(-settings.intake_records // 20) if "intake" in stages else 0)
            + (1 if "eval" in stages else 0)
        )
        print(f"\n  DRY RUN -- would make roughly {approx_calls} LLM calls.")
        return

    out_dir = settings.output_dir / spec.key
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    assets: dict[str, object] = {}

    try:
        if "corpus" in stages:
            print("\n  [1/4] corpus ...", flush=True)
            assets["corpus"] = spec.build_corpus(out_dir)
        if "intake" in stages:
            print("  [2/4] intake ...", flush=True)
            assets["intake"] = spec.build_intake(out_dir)
        if "tables" in stages:
            print("  [3/4] mock API tables ...", flush=True)
            assets["mock_api"] = spec.build_seed_tables(out_dir)
        if "eval" in stages:
            print("  [4/4] golden eval set ...", flush=True)
            assets["eval"] = spec.build_eval_set(out_dir, [d.title for d in docs])
    except LLMError as exc:
        # Write what we have so the run is not a total loss, then report.
        write_manifest(
            out_dir,
            domain=spec.name,
            seed=settings.seed,
            provider=settings.provider,
            model=model_name(),
            assets=assets,
            public_sources=spec.public_sources,
            partial=True,
        )
        sys.exit(
            f"\n  FAILED: {exc}\n"
            f"  Partial output and manifest written to {out_dir.resolve()}.\n"
            f"  Re-run the same command; completed corpus documents are skipped."
        )

    # The manifest is the provenance record M8 asks you to defend your data
    # with. v1.0.0 only wrote it from an orchestration path the CLI never
    # called, so it was never produced at all.
    write_manifest(
        out_dir,
        domain=spec.name,
        seed=settings.seed,
        provider=settings.provider,
        model=model_name(),
        assets=assets,
        public_sources=spec.public_sources,
    )

    print(f"\n  done in {time.time() - started:.0f}s -> {out_dir.resolve()}")
    print("  manifest   : manifest.json")


def main() -> None:
    args = build_parser().parse_args()
    apply_overrides(args)

    stages = {s.strip() for s in args.only.split(",") if s.strip()}
    unknown = stages - set(_STAGES)
    if unknown:
        sys.exit(f"Unknown stage(s): {', '.join(sorted(unknown))}")

    if not args.dry_run:
        preflight(stages)

    keys = sorted(REGISTRY) if args.domain == "all" else [args.domain]
    for key in keys:
        run_domain(key, stages, args.dry_run)


if __name__ == "__main__":
    main()
