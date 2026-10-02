# Changelog

All notable changes to the Capstone Data Toolkit.

---

## [1.0.4] — 2026-10-02

Consistency release for CareFlow, LexOps, WealthPilot and ShopSense. The
PlantGuard report behind v1.0.3 was that a policy document referred to data
no table held. The same audit of the other four problem statements found the
same fault in each, and a second one underneath it: most figures in the
corpus were invented by the model at generation time, so a document, a mock
API table and an eval answer could each say something different.

Each domain now states its policy once, as constants at the top of its
module. The document prompts quote those constants, the mock API tables
store them, and the hand-written eval answers are computed from them.

### Do I need to regenerate?

**Mock API tables: run once, nothing breaks.** Every table that existed
before this release is byte-identical. This adds 41 tables beside them:

```bash
python generate.py --domain <yours> --only tables
```

**Corpus: recommended.** Documents written by an earlier version carry
figures no table agrees with. Regenerate with `--only corpus --no-resume`,
or keep your documents and take every figure from the tables instead.

**Intake and eval: recommended.** Earlier intake records name patients,
counterparties, applicants and orders that are in no table, and earlier eval
answers were not checked against the corpus. Regenerate with
`--only intake,eval --no-resume`, after the corpus.

`python -m tests.validate_data --domain <yours>` reports which of these
apply to the data you have.

---

### Fixed — all domains

**Eval answers were written without the documents.** The eval prompt gave
the model the corpus titles only, so "expected" answers quoted windows, fees
and thresholds that appeared in no document. Checked against a real
PlantGuard run: four of eight factual cases cited figures absent from the
manuals they named. The eval stage now passes the corpus text, repairs
misquoted `must_cite` titles, and discards a factual or multi-hop case whose
figures are not in the documents it cites. The result records
`grounded_in_corpus` and how many cases were dropped.

**Two intake batches could be written about the same row.** Each batch drew
its sample independently. Batches now walk one shuffled order and pass over
any order or application already written about, including records on disk
from a run that is being resumed.

### Fixed — CareFlow

- **The co-pay calculator had nothing to calculate with.** No procedures, no
  prices, no imaging or lab co-pays. Added `procedures`, `plan_copays` and
  `preauth_rules`; the cost-share schedule and pre-authorisation matrix are
  generated from them.
- **The slot finder had no slots, providers or sites.** `provider_id` and
  `patients.primary_site` pointed at nothing. Added `providers`, `sites` and
  `appointment_slots`.
- **Referrals named no procedure, and Priority had no SLA.** Added
  `urgency_bands` and `referral_details`: procedure, pre-authorisation
  status, assigned provider and due date, each agreeing with the rule for its
  procedure and plan.
- **No per-patient memory.** Added `patient_interactions`.
- **Intake messages named patients who do not exist.** They are now written
  about registered patients, with that patient's plan and member number.
- **"Urgent within 24 hours" and a due date three days later.** The SLA is
  in business days, so the referral policy now says so: Urgent is due by the
  end of the next working day.

### Fixed — LexOps

- **The playbook existed only as prose.** Preferred, fallback and walk-away
  positions and the points for each were invented per run. Added
  `playbook_positions`, `clause_families` and `approval_tiers`; the overview,
  the risk-scoring methodology and all sixteen clause documents are generated
  from them.
- **No contract had clauses, so nothing could be scored.** Added
  `contract_clauses` (every contract's position on every clause type) and
  `contract_risk` (score, band, approval tier, approver).
- **Renewal tracking had no dates and counterparties had no history.** Added
  `contract_renewals` and `negotiation_history`. A negotiation round about a
  contract ends at the position that contract's clause actually holds.
- **Intake requests named invented companies.** They now carry a real
  `counterparty_id`, and `risk_band` is spelled as the tables spell it
  (`Standard`, `Deviation`, `Escalation`) and never below what the annual
  value and the named deviations require.

### Fixed — WealthPilot

- **No loan applications.** `applicants` held businesses but no request: no
  amount, tenor or purpose, so DSCR could not be computed. Added
  `loan_applications` and `underwriting_reference`, the policy's answer for
  each: DSCR, ratios, grade, rate, reason codes, outcome and who must sign.
- **Thresholds, grades, sector floors and reason codes were prose only.**
  Added `policy_limits`, `risk_grades`, `sector_policies`,
  `approval_authorities`, `reason_codes` and `reference_rates` (base rate and
  FX for the M2 conversion tool).
- **Maximum tenor and collateral cover were stated but never tested.** A
  tenor longer than the grade or the sector allows, or collateral below the
  grade's cover, now makes an application borderline (`TENOR_ABOVE_LIMIT`,
  `COLLATERAL_SHORTFALL`). A revenue gap above 25% carries `FRAUD_HOLD`, and
  an application missing a figure is never approvable
  (`INCOMPLETE_APPLICATION`).
- **A decline was routed "auto".** Only an approval within the automatic
  limit is automatic; a decline needs human sign-off, in the tables, the
  intake labels and the eval cases alike.
- **`past_decisions.human_signatory` pointed at nobody.** Added
  `signatories`.
- **Intake DSCR labels were the model's own arithmetic.** Applications are
  now written about real rows, and the figures, the arrival time and every
  `ground_truth` label are computed from the tables by the rule that fills
  `underwriting_reference`, so a complete application carries exactly the
  reference's labels.
- **The matched bias pairs had no stated outcome.** Three pairs now carry
  the computed DSCR, grade, outcome and authority.

### Fixed — ShopSense

- **The refund calculator had no rules.** Restocking fees, return windows
  for five of eight categories, pickup fees and refund timelines were
  invented per run. Added `category_policies`, `refund_rules`,
  `refund_processing_times`, `refund_authority` and `policy_limits`.
- **Delivery promises had no service or zone, and delays no compensation.**
  Added `delivery_services`, `delay_compensation` and `order_fulfilment`:
  one row per order with promised and delivered dates, days late, credit
  due, last return date and warranty end.
- **`products.seller_id` and `shipments.carrier` pointed at nothing.** Added
  `sellers` and `carriers`.
- **Half of the refund/replace API was missing, and the goodwill rule could
  not be checked.** Added `replacements` and `goodwill_credits`.
- **No per-customer memory.** Added `support_tickets` (past tickets, each
  agreeing with the refund, replacement or credit it led to, and linked only
  to refunds the policy allows) and `customer_profiles` (preferences and
  fraud-review status).
- **Escalation rules were prose only.** Added `escalation_triggers`.
- **Intake tickets named invented orders.** They are now written about real
  orders. The customer, timestamp, category and the triggers that follow
  from data (refund above the cap, third contact, account under review) are
  set from the tables, whatever shape the model gives its fields.
  `ground_truth` gains `escalation_triggers`.

### Added

- 41 mock API tables: 10 CareFlow, 7 LexOps, 9 WealthPilot, 15 ShopSense.
  Schemas, joins and worked examples are in `capstone-data-toolkit/README.md`.
- Hand-written eval cases with computed answers: `CAREFLOW-EV-906`, `-907`;
  `LEXOPS-EV-906`; `WEALTHPILOT-EV-906` to `-910`; `SHOPSENSE-EV-906` to
  `-910`. `CAREFLOW-EV-904`, `LEXOPS-EV-901`, `-904`, `WEALTHPILOT-EV-901`,
  `-902` and `SHOPSENSE-EV-901`, `-904` now state exact figures.
- Intake fields: `counterparty_id` (LexOps); `applicant_id`,
  `requested_tenor_months` and `declared_financials.collateral_value_inr`
  (WealthPilot); `escalation_triggers` (ShopSense).
- Validator: checks for all four domains that documents, tables and intake
  records agree; a check that eval answers are grounded in the corpus; and a
  `NOTE` level for known limits of the original tables, each naming the
  table to use instead.
- `DomainSpec.references`, `stream()`, `private_faker()`,
  `finalize_intake_record()` and `intake_sample()` for domain authors, and
  `datagen/grounding.py`.
- `DATAGEN_EVAL_CORPUS_CHARS` (default 160,000): corpus text given to the
  model when writing eval cases. Lower it for a small local model.
- Worked examples in the cost-share, credit-policy, risk-scoring and returns
  documents are computed in code and handed to the model, so a document
  cannot get its own arithmetic wrong.
- Thirty-two regression checks (113 in total).

### Changed

- **`--fresh-table-rng` reconciles more.** CareFlow: appointment specialty
  matches the provider, appointments fall in working hours and not on a
  Sunday, deductible met never exceeds the deductible. LexOps:
  `contracts.risk_score` is the computed score and a contract's status
  follows its dates. WealthPilot: signatories are active and have authority
  for the amount, grades and reason codes agree with the policy, and
  `bank_statements` becomes up to 18 consecutive months per applicant.
  ShopSense: orders still in flight are recent, scan times follow the order,
  refunds are requested inside the period their reason allows, never exceed
  what was paid in total, and are never automatic for an account under
  review; non-warranty categories carry no warranty. Default mode is
  untouched.
- The validator summary counts notes: `22 passed, 3 notes, 0 warnings, 0
  failed`.

### Known limits

- The original tables are unchanged in default mode, so they still contradict
  the policy in places: 795 of 900 CareFlow appointments pair a provider with
  another specialty; `contracts.risk_score` is random; WealthPilot applicants
  have fewer than 18 bank statements; 126 ShopSense refunds exceed their
  order value. The validator lists each as a `NOTE`. `--fresh-table-rng`
  removes them, at the cost of different rows from teams on the default.
- Policy figures (fees, floors, points, thresholds) are invented for
  fictional companies. They are internally consistent, not industry
  benchmarks.
- `--fresh-table-rng` does not invent missing rows: a returned ShopSense
  order may still have no refund, and a scheduled CareFlow referral may have
  no appointment.
- A model can still ignore a figure it is given. The validator's document
  checks catch the common cases; the tables are the reference.
- The corpus, intake and eval stages were tested offline with a stub
  provider, not against a live model.

---

## [1.0.3] — 2026-10-02

Data-completeness release for PlantGuard. Two participants reported data the
problem statement needs and the toolkit never generated: the factors behind
asset criticality, and the technicians that work orders are assigned to. An
audit of PlantGuard against its milestones found the same kind of gap in four
more places. A crash on a half-installed virtual environment is fixed too, and
there is now a command that checks whether the data you generated is complete.

### Do I need to regenerate?

**Mock API tables: run once, nothing breaks.** The four existing PlantGuard
tables (`assets`, `telemetry`, `work_orders`, `inventory`) and every table in
the other four domains are byte-identical to v1.0.2. This adds ten PlantGuard
tables beside them:

```bash
python generate.py --domain plantguard --only tables
```

**Corpus (PlantGuard): optional.** Ten documents now receive fixed figures
that match the tables: `maintenance-planning`, `spares-procurement` and the
eight `manual-*` files. To pick them up, delete those files from
`data/plantguard/corpus/markdown/` and `corpus/pdf/` and re-run; everything
else is skipped. If you keep your current corpus, take criticality factors,
alarm limits and part numbers from the tables, not from the documents.

**Intake (PlantGuard): optional.** Records generated before this release may
name asset tags that are not in `assets`. Regenerate with
`--only intake --no-resume` if your tools look assets up by tag.

---

**Check what you have.** One command reports what is missing or out of date
and prints the fix for each item:

```bash
python -m tests.validate_data --domain <yours>
```

---

### Fixed — startup

**`ModuleNotFoundError: No module named 'pydantic_core'` killed the CLI with a
twelve-line traceback.** The cause is a half-installed virtual environment:
`pydantic` present, its compiled companion missing (an interrupted install, or
packages installed by a different Python than the one running). `generate.py`
now checks its dependencies before importing anything and prints the Python in
use, whether a virtual environment is active, and the repair command:

```bash
python -m pip install --force-reinstall --no-cache-dir -r requirements.txt
```

The READMEs now say `python -m pip` rather than bare `pip`, which is what
keeps the install and the interpreter from diverging in the first place.

### Fixed — PlantGuard data the problem statement needs

**Criticality had no factors behind it.** Clause 2.1 of the maintenance
planning standard assigns class A/B/C "based on safety risk, environmental
impact, and production downtime cost", but no table carried any of the three,
so the M2 downtime-cost calculator had no rate to use and teams invented their
own. Added `criticality_matrix` (the class rules, with a default hourly rate
and inspection interval per class) and `asset_criticality` (each asset's own
three factors and its downtime cost in rupees per hour). An asset takes the
most severe class indicated by any one factor. The maintenance planning
document is now generated from the same matrix.

**Technicians did not exist.** `work_orders.technician_id` pointed at forty
IDs that resolved to nothing, so the M2 technician-scheduling calendar had no
people, skills or availability. Added `technicians` (trade, level, shift and
permit certifications) and `technician_calendar` (shift, status, booked and
free hours for 28 days). Every existing `technician_id` now resolves.

**Found in the audit that followed:**

- **Work orders could not be scheduled or costed.** No required skill, no
  duration, no date, no failure, no part. Added `work_order_details`, one row
  per work order, consistent with the assigned technician's skills and
  certifications and with the calendar's booked hours.
- **No ERP behind the procurement agent (M6).** `inventory` named a supplier
  tier but there were no suppliers and no purchase orders. Added `suppliers`,
  `part_suppliers` and `purchase_orders`. No order above ₹200,000 is
  auto-raised, matching the procurement policy, and some low-stock parts are
  left with no open order for the agent to act on.
- **Manuals cited parts and limits the tools could not find.** The model was
  told to invent part numbers and alarm setpoints. Each manual now receives
  real part numbers from `inventory` and the limits in the new `asset_classes`
  table.
- **No pressure history.** Manuals, the alarm procedure and intake readings
  all refer to pressure; `telemetry` has none. Added `telemetry_pressure` for
  the four asset classes with a pressure system.
- **Intake events named machines that do not exist.** The prompt gave one
  example tag and let the model invent the rest. It now lists the real tags.

### Fixed — manifest

**A partial run erased the record of earlier ones.** The Sourcing Guide says
the manifest merges across runs; it did not. `--only tables` after a full run
left a manifest listing only the tables. Assets recorded by earlier runs are
now kept for as long as their files exist.

### Added

- **`tests/validate_data.py`** — checks a generated dataset against what this
  version produces, for one domain or all five:

  ```bash
  python -m tests.validate_data --domain plantguard
  python -m tests.validate_data --domain all
  ```

  It verifies that every corpus document exists as markdown and PDF, that
  intake records carry their fields and `ground_truth`, that every table has
  the right columns, types and row counts and that its IDs resolve, that the
  eval set holds its hand-written cases, and that the manifest is present.
  PlantGuard and CareFlow get extra checks that documents and tables agree.
  Results are `PASS`, `WARN` (usable, typically data from an older version) or
  `FAIL` (missing or malformed), each with the command that fixes it. Exit
  status 1 on any failure; `--strict` fails on warnings too. `generate.py`
  prints the command at the end of every run.
- `intake_fields` and `intake_truth_fields` on every domain: the record
  fields its intake prompt asks for, declared so the validator can check them.
- Ten PlantGuard tables: `asset_classes`, `criticality_matrix`,
  `asset_criticality`, `technicians`, `technician_calendar`,
  `work_order_details`, `telemetry_pressure`, `suppliers`, `part_suppliers`,
  `purchase_orders`. Schemas are in `capstone-data-toolkit/README.md`.
- `--schema`: prints everything a full run produces for a domain — the corpus
  documents, the intake and eval fields, and every table's row count, columns
  and types. No API key, nothing written.
- "What data to expect" and "Check your data" in the top-level README, and a
  column-level "Data reference" in the toolkit README, covering all five
  domains.
- `DomainSpec.corpus_instruction()`: a hook for adding table facts to a
  document prompt without building tables during `--dry-run`.
- Forty-three regression checks (81 in total). They include one that fails
  if a table, a PlantGuard column or an expected count is missing from the
  README, and one that damages a generated dataset and confirms the validator
  reports each fault.

### Changed

- The new tables use private random streams, one per table group, so they
  cannot disturb the original four and a future table cannot reshuffle these.
- The referential-integrity test now treats a table as owning a key only when
  its first column is unique, and ignores empty optional references. The old
  rule mistook composite-key tables for key owners.

### Known limits

The four original PlantGuard tables still draw each column independently (an
open work order can carry an old `raised_on`; `lead_time_days` does not follow
`supplier_tier`). They stay as they are until 1.1.0 so existing work is not
disturbed.

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
