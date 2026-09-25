# Changelog

All notable changes to the Capstone Data Toolkit.

---

## [1.0.2] — 2026-09-24

Reliability release. Prompted by a PlantGuard run that failed repeatedly with
`503 Service Unavailable` and `429 Too Many Requests` from Gemini's free tier.
The follow-up audit of all five domains found eval cases that fail correct
answers, and corpus prompts and mock tables that contradict each other.

### Do I need to regenerate?

**Mock API tables: no.** Byte-identical to v1.0.1 by default, verified across
all five domains. The consistency fixes below apply only with
`--fresh-table-rng`.

**Eval set: yes, if you use the hand-written cases.** Several
`must_not_contain` lists were rewritten (see below). Rebuild just that asset:

```bash
python generate.py --domain <yours> --only eval --no-resume
```

**Corpus: optional.** Documents that now receive fixed figures (CareFlow
`copay-schedule`, ShopSense category addenda, PlantGuard equipment manuals)
only match the mock tables if they are regenerated. Delete those files under
`data/<domain>/corpus/` and re-run; everything else is skipped.

---

### Fixed — provider failures

**Runs died on transient Gemini errors.** Four attempts with 1-2-4-8s waits
(~15s total) could not outlast a free-tier `503` (model overloaded) or a `429`
(per-minute quota, which resets on a 60s window). The retry loop in
`datagen/llm.py` now:

- retries 408/429/500/502/503/504 up to `max_retries` (default 4 → **8**),
  with exponential backoff capped at `max_backoff` (60s);
- honours the provider's requested delay (Gemini's `RetryInfo.retryDelay` or
  a standard `Retry-After` header);
- paces Gemini calls `min_request_interval` apart (default 6s), staying under
  the free tier's ~10 RPM instead of recovering after the fact;
- falls back to `gemini_fallback_model` (default `gemini-flash-lite-latest`,
  a separate quota bucket) at once on `429`, or after half the retry budget on
  repeated `503`, and **stays on it for the rest of the run**, so later calls
  do not pay the same failed-retry toll;
- fails fast with a clear message when the **daily** quota (`...PerDay...`)
  is exhausted, since waiting cannot help;
- logs `HTTP <status> from <model> [<quota id>]` per attempt instead of a
  truncated URL.

The fallback is skipped when it equals `gemini_model`, and dropped with a
warning if the provider returns 404 for it. Set
`DATAGEN_GEMINI_FALLBACK_MODEL=` to disable it.

### Fixed — resume

**Intake and eval were not resumable.** A `429` on the last intake batch
discarded every record already generated, and the eval set was rebuilt on
every run. Intake now checkpoints `records.jsonl` after each batch, saves what
it has before re-raising a provider failure, and tops up from disk on re-run
with dense, continuous `record_id`s. An eval set already on disk with
`eval_items` cases is skipped. `--no-resume` still forces a rebuild of both.

**`--domain all` stopped at the first failure.** A quota error in one domain
now marks it incomplete and the run continues; the CLI exits non-zero at the
end and lists the domains to re-run.

### Fixed — eval correctness

**Hand-written cases penalised correct answers.** `must_not_contain` is a
substring match, but several lists banned words a correct refusal naturally
echoes from the question: "you may not **suppress** the alarm" (PlantGuard),
"I can't say whether it is **enforceable**" (LexOps), "cannot be **approved**
without a signatory" (WealthPilot), "I can't advise on **dose**" (CareFlow),
"no **clause** covers this" (WealthPilot). About twenty entries across all
five domains were replaced with phrases only a wrong answer contains. The rule
is now documented on `EvalCase`.

### Fixed — corpus and mock tables disagreed

**Prompts now carry the figures the tables and eval set depend on.**

- **CareFlow** `copay-schedule` receives each plan's deductible, coinsurance,
  out-of-pocket maximum and co-pays from the same source as the `plans` table
  (`CAREFLOW-EV-904` checks MERIDIAN-BRONZE coinsurance).
- **ShopSense** category addenda receive the return windows fixed by the
  general policy (Electronics 15 days, Apparel 45, Groceries non-returnable,
  Home & Kitchen 30), so the documents no longer contradict each other and
  `SHOPSENSE-EV-904` has a correct answer.
- **PlantGuard** equipment manuals set alarm thresholds above the healthy
  band present in the `telemetry` table; previously a manual could put its
  warning level below normal operation, so every asset alarmed constantly.

**Mock tables contradicted themselves** (with `--fresh-table-rng` only). Every
column was drawn independently. A new `DomainSpec.reconcile_tables()` hook now
fixes cross-table facts without drawing from the RNG:

| Domain | Before | After |
|---|---|---|
| WealthPilot | 75 declined loans with an approved amount; 81 approvals with a decline reason | 0; withdrawn decisions use `WITHDRAWN_BY_APPLICANT` |
| ShopSense | 1,328 / 1,500 order values ≠ price × quantity; 40 refunds above ₹2,000 decided by `auto`; cancelled orders scanned `delivered`; refunds above order value | 0 — approvers follow the refund authority matrix |
| CareFlow | 228 `completed` appointments in the future, 146 `scheduled` in the past | 0 |
| LexOps | uncapped-liability contracts scored below 30; signed envelopes on draft contracts | uncapped scores > 70; signed only on executed/expired |
| PlantGuard | motor current jumped ±20 A hour to hour | stable per-asset baseline plus noise and fault load |

### Changed

- `--fresh-table-rng` now means "clean single draw **and** reconciled tables".
  It still changes table contents relative to v1.0.0/v1.0.1, so it remains a
  new-projects-only flag. Its planned removal in 1.1.0 should make this the
  default rather than drop the behaviour.
- `.gitignore` ignores `capstone-data-toolkit/data/`; generated output is no
  longer tracked.

### Added

- Settings: `gemini_fallback_model`, `max_backoff`, `min_request_interval`
  (all overridable with `DATAGEN_*` environment variables).

### Note on the test suite

`python -m tests.test_regressions` is the authoritative runner (38 checks,
all passing). Running the same file under `pytest` reports every function as
passed even when a `check()` fails, because the checks record results rather
than `assert`.

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
