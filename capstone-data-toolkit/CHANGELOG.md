# Changelog

All notable changes to the Capstone Data Toolkit.

---

## [1.0.1] — 2026-08-08

Bug-fix release. Found by a participant report that `manifest.json` was never
written; the audit that followed surfaced two problems more serious than the
one reported.

### Do I need to regenerate?

**Mock API tables: no.** They are byte-identical to v1.0.0 by default,
verified across all five domains. Nothing you built against them breaks.

**Corpus, intake, eval: no, but re-running is now cheap.** Completed corpus
documents are skipped on re-run, so topping up costs only the missing pieces.

**To get your `manifest.json` without regenerating anything else:**

```bash
python generate.py --domain <yours> --only tables
```

The manifest is written on every run and records whatever assets exist.

---

### Fixed — blockers

**`manifest.json` was never written, for any problem statement.**
`DomainSpec.generate()` was the only caller of `write_manifest()`, and nothing
ever called `generate()`. The CLI reimplemented the orchestration and omitted
the manifest step. The manifest is now written by the CLI on every run,
including on failure (flagged `"complete": false`), and carries a
`toolkit_version` field.

**Infinite loop in intake generation.**
`build_intake` looped `while len(rows) < target` with no exit condition. A
model returning an empty array — safety filter, malformed JSON, a bad free-tier
day — spun forever. Measured at 2.3 million calls in 8 seconds against a stub;
against a real API this drains an entire quota or hangs indefinitely. Now
bounded by `max_intake_attempts` (default 30), stops after three consecutive
unproductive batches, and reports any shortfall rather than failing silently.

**Provider safety blocks crashed the run with an uncaught `KeyError`.**
A blocked Gemini prompt returns no `candidates` key at all. This is not rare:
clinical escalation standards (CareFlow) and hazardous-procedure SOPs
(PlantGuard) trip safety classifiers regularly. The run died with
`KeyError: 'candidates'` — an error that tells a participant nothing. Now
raises a typed `ContentBlocked`, the offending document is skipped and named in
the output, and the rest of the run continues. OpenRouter and Ollama response
shapes are normalised the same way.

### Fixed — quota and time

**`--corpus-docs N` was ignored.** Requested 4, generated 19. The cap reached
only the CLI's display line, never `build_corpus`. Both the README and the
Sourcing Guide recommend this flag for cheap iteration; it now works.

**No resume.** A run that died at document 40 of 50 regenerated all 50 on
retry. Completed documents are now skipped; `--no-resume` restores the old
behaviour.

**Seed tables were built twice per invocation** — once to print table names,
once for real — and once during `--dry-run`, which is advertised as free. That
meant 20,868 PlantGuard rows built just to render a header. Table names are now
declared as class attributes and the build is cached. Dry-run time for all five
domains: 1021ms → 595ms.

### Fixed — correctness

- `record_id` skipped every other integer (`len(rows)+i` double-counted while
  appending inside the loop). IDs are now dense and sequential.
- Short batches burned one API call per record with no guard.
- Eval category distribution is now validated against what the Sourcing Guide
  promises per domain, with a warning when the model ignores the requested mix.
  A set of twenty `factual` questions looks complete and tests nothing.

### Removed

- `DomainSpec.generate()` — dead, and divergent: it consumed RNG differently
  from the CLI, so wiring it in would have silently changed everyone's table
  data. Removed rather than repaired.
- `writers.checksum()` — dead.
- `settings.concurrency` — declared but never used; implied parallelism that
  does not exist.

### Added

- **`tests/`** — an offline regression suite, one test per bug above, plus
  standing invariants for referential integrity, determinism, and
  declared-vs-built table names. Runs in under a minute with no API key:

  ```bash
  python -m tests.test_regressions
  ```

  `tests/stub_provider.py` simulates the failure shapes a free tier actually
  produces (refusals, empty batches, short batches, dict-wrapped responses), so
  the LLM-dependent paths can be exercised without a provider. Every blocker in
  this release lived behind an API call and survived because those paths were
  never tested. Use it on your own domain changes.

- `--no-resume`, `--fresh-table-rng`, `--version` flags.
- `settings.max_intake_attempts`, `settings.resume`, `settings.legacy_table_rng`.

### Note on `--fresh-table-rng`

v1.0.0's table data came from a second, redundant RNG draw. Caching the build
would have changed everyone's output, so by default v1.0.1 reproduces the
discarded first draw to stay byte-compatible. On a new project, pass
`--fresh-table-rng` for the clean single-draw behaviour. This flag exists
purely for mid-project compatibility and will be removed in 1.1.0.

---

## [1.0.0] — 2026-08-04

Initial release. Four data assets (RAG corpus, intake records, mock API tables,
golden eval set) across five capstone problem statements, with a
provider-agnostic generator supporting Gemini AI Studio, OpenRouter, and Ollama.
