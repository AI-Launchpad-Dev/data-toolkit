# Project Data Toolkit

**Applied AI Professional Certification Program · IIT Hyderabad**

This repository generates the data you need for your project. You pick your problem statement, run one command, and get four ready-to-use data assets: a document corpus for RAG, raw intake records, mock API tables, and a golden evaluation set.

You do not need to invent data from scratch. Read the **Data Sourcing Guide** alongside this repo. It tells you which public datasets to use for your problem statement, and this toolkit generates the parts nobody publishes.

---

## Find your domain

Every command takes a `--domain` flag. Use the one that matches your problem statement.

| Problem statement | `--domain` | Corpus docs | Mock API tables |
|---|---|---|---|
| CareFlow: AI Care Coordination Assistant | `careflow` | 14 | 14 tables: patients, plans, appointments and open slots, providers, referrals, procedures, pre-authorisation rules, co-pays, interaction history |
| LexOps: Contract Intelligence & Compliance Copilot | `lexops` | 19 | 10 tables: counterparties, contracts, signature requests, the playbook as data, clause positions and risk per contract, renewals, negotiation history |
| WealthPilot: SME Loan Underwriting Assistant | `wealthpilot` | 13 | 13 tables: applicants, bureau reports, bank statements, loan applications, underwriting reference, risk grades, sector policies, approval authorities, past decisions |
| ShopSense: Customer Care & Order Operations | `shopsense` | 14 | 20 tables: customers, products, orders, shipments, refunds, replacements, goodwill credits, policy tables, sellers, carriers, past tickets |
| PlantGuard: Predictive Maintenance Copilot | `plantguard` | 13 | 14 tables: asset registry, sensor history, work orders, technicians, inventory and purchasing |

Exact files, row counts and columns for your domain are in [What data to expect](#what-data-to-expect).

---

## Repository layout

```
.
├── README.md                    ← you are here
├── CHANGELOG.md                 ← release history (read this if you used v1.0.0)
├── .gitignore
└── capstone-data-toolkit/       ← all commands run from inside this folder
    ├── generate.py              ← the command you run
    ├── requirements.txt
    ├── .env.example             ← copy to .env and add your API key
    ├── README.md                ← detailed toolkit reference
    ├── CHANGELOG.md
    ├── datagen/
    │   ├── config.py            ← settings, read from .env
    │   ├── llm.py               ← provider client (Gemini / OpenRouter / Ollama)
    │   ├── writers.py           ← markdown, PDF, JSONL, CSV, manifest output
    │   └── domains/
    │       ├── base.py          ← shared logic for all five domains
    │       ├── careflow.py
    │       ├── lexops.py
    │       ├── wealthpilot.py
    │       ├── shopsense.py
    │       └── plantguard.py    ← one file per problem statement
    └── tests/
        ├── validate_data.py     ← checks the data you generated
        ├── stub_provider.py     ← fake LLM, so tests need no API key
        └── test_regressions.py  ← offline test suite for the toolkit code
```

To customise the data for your problem statement, edit your domain's file in `datagen/domains/`. You should not need to touch anything else.

---

## Quick start

You need **Python 3.10 or newer** (tested on 3.12).

### 1. Clone and enter the toolkit folder

```bash
git clone <this-repo-url>
cd <repo-name>/capstone-data-toolkit
```

Every command below runs from inside `capstone-data-toolkit/`. Running from the repository root will fail with `ModuleNotFoundError: No module named 'datagen'`.

### 2. Create a virtual environment and install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

If anything fails to import later (for example `No module named 'pydantic_core'`), the install is incomplete. See Troubleshooting Q10.

### 3. Get data with no API key at all

The mock API tables are generated locally, with no LLM. This is enough to start building your M2 tools today.

```bash
python generate.py --domain <your-domain> --only tables
```

### 4. Add your API key for the LLM-generated assets

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

Open `.env` and set two lines:

```
DATAGEN_GEMINI_API_KEY=<your key from https://aistudio.google.com/apikey>
DATAGEN_GEMINI_MODEL=gemini-flash-latest
```

> ⚠️ **You must change `DATAGEN_GEMINI_MODEL`.** The file ships with `gemini-2.0-flash`, which Google shut down on 1 June 2026. Left unchanged, every LLM call fails. `gemini-flash-latest` is an alias Google keeps pointed at a current Flash model. If you prefer a pinned model, use a current stable ID from https://ai.google.dev/gemini-api/docs/models.

The `.env` file must sit inside `capstone-data-toolkit/`, next to `generate.py`. It holds your key, so never commit it.

### 5. Preview, then generate

```bash
python generate.py --domain <your-domain> --dry-run    # shows the plan, costs nothing
python generate.py --domain <your-domain>              # generates everything
```

Your data lands in `capstone-data-toolkit/data/<your-domain>/`.

### 6. Check that everything was generated

```bash
python -m tests.validate_data --domain <your-domain>
```

It ends with `READY` or `NOT READY` and prints the command that fixes each problem it finds. See [Check your data](#check-your-data).

---

## What you get

```
data/<your-domain>/
├── corpus/
│   ├── markdown/*.md        policy documents, clean format
│   ├── pdf/*.pdf            the same documents as PDF (index both)
│   └── index.json
├── intake/records.jsonl     messy raw inputs, each with a ground_truth block
├── mock_api/*.csv, *.json   tables behind your tools
├── eval/golden_set.json     20 graded test cases, adversarial ones included
└── manifest.json            where the data came from, seed, licences
```

| Asset | First used in | What to do with it |
|---|---|---|
| Corpus | M3, M4 | Index it and retrieve over it. Test your chunker on the PDFs, not just the markdown. |
| Intake records | M1 | Parse them into your Pydantic models. The `ground_truth` block is your accuracy metric. Don't discard it. |
| Mock API tables | M2, M6 | Back your tool functions with these, then expose them over MCP in M6. |
| Golden eval set | M8 (start at M4) | Score your system against it. Start using it as soon as retrieval works, not the week of your presentation. |
| `manifest.json` | M8 | Evidence of where your data came from. Reviewers will ask. |

---

## What data to expect

Run this to see everything your domain produces: the corpus documents, the intake and eval fields, and every table with its row count, columns and types. It needs no API key and writes nothing:

```bash
python generate.py --domain <your-domain> --schema
```

### The three LLM-generated assets (same shape in every domain)

**Corpus** (`corpus/markdown/*.md`, `corpus/pdf/*.pdf`). Each document is listed in `corpus/index.json`:

| Field | Type | Meaning |
|---|---|---|
| `slug` | str | File name without extension |
| `title` | str | Document title. Eval cases cite documents by this title. |
| `section` | str | Document group, e.g. `safety`, `policy`, `equipment_manual` |
| `markdown`, `pdf` | str | Relative paths to the two copies |
| `chars` | int | Length of the document body |

**Intake records** (`intake/records.jsonl`, one JSON object per line, 200 by default). The toolkit adds `record_id`. Every record has a `ground_truth` object: your M1 accuracy labels. About one record in six is deliberately missing a field.

The IDs in a record are real rows in the mock API tables: `patient_ref` in `patients`, `counterparty_id` in `counterparties`, `application_id` in `loan_applications`, `order_ref` in `orders`, `asset_tag` in `assets`. Your tools can look up every record. Labels that follow from the data are computed, not written by the model: the WealthPilot DSCR and risk band, and the ShopSense escalation triggers for refund size, repeat contact and accounts under review.

| Domain | Record fields | `ground_truth` fields |
|---|---|---|
| `careflow` | `channel`, `received_at`, `raw_text`, `patient_ref`, `insurance_id_stated` | `urgency`, `specialty`, `seeks_clinical_advice`, `missing_fields` |
| `lexops` | `request_id`, `channel`, `requester_role`, `received_at`, `raw_text`, `counterparty_id`, `counterparty_name`, `contract_type`, `annual_contract_value_usd`, `attached_clause_text` | `clause_types_present`, `deviations`, `risk_band`, `requires_human_review` |
| `wealthpilot` | `application_id`, `applicant_id`, `channel`, `received_at`, `raw_narrative`, `business_name`, `sector`, `requested_amount_inr`, `requested_tenor_months`, `declared_financials`, `bureau_score` | `dscr`, `meets_dscr_floor`, `risk_band`, `requires_human_signoff`, `missing_fields` |
| `shopsense` | `ticket_id`, `channel`, `received_at`, `raw_text`, `order_ref`, `customer_ref` | `intent`, `category`, `sentiment`, `claimed_amount_inr`, `escalation_triggers`, `requires_human`, `missing_fields` |
| `plantguard` | `event_id`, `source`, `received_at`, `raw_text`, `asset_code`, `asset_tag`, `readings` (`vibration_mm_s`, `temp_c`, `pressure_bar`, `current_a`) | `priority`, `probable_fault`, `safety_critical`, `requires_permit`, `missing_fields` |

**Golden eval set** (`eval/golden_set.json`, a list of 20 cases):

| Field | Type | Meaning |
|---|---|---|
| `id` | str | `<DOMAIN>-EV-0xx` are model-written; `-EV-9xx` are hand-written: adversarial cases, and cases whose exact answer is computed from the same figures the documents and tables use |
| `question` | str | What the user asks |
| `expected` | str | What a correct answer does |
| `category` | str | `factual`, `multi_hop`, `unanswerable`, `guardrail`, `injection` (WealthPilot adds `bias_probe`) |
| `must_cite` | list[str] | Corpus document titles a correct answer cites |
| `must_not_contain` | list[str] | Phrases only a wrong answer would contain |
| `expected_route` | str | `auto`, `human_review` or `refuse` |

The eval set is grounded in your own corpus. The model sees the text of your documents when it writes a case, and a factual or multi-hop case whose answer cites figures that are not in the documents it cites is discarded. Generate the corpus first, and regenerate the eval set (`--only eval`) if you regenerate the corpus.

### Mock API tables (no LLM, identical for everyone on the same seed)

Each table is written twice: `mock_api/<table>.csv` and `mock_api/<table>.json`. Empty values are blank in CSV and `null` in JSON. Dates are ISO strings anchored to a frozen "today" of **2026-08-01**, so treat that date as "now" in your tools.

| Domain | Tables (rows at the default seed) |
|---|---|
| `careflow` | `plans` (4), `patients` (400), `appointments` (900), `referrals` (300), `specialties` (8), `urgency_bands` (4), `sites` (14), `providers` (60), `appointment_slots` (480), `procedures` (24), `preauth_rules` (96), `plan_copays` (16), `referral_details` (300), `patient_interactions` (600) |
| `lexops` | `counterparties` (120), `contracts` (260), `signature_requests` (80), `clause_families` (8), `playbook_positions` (16), `approval_tiers` (3), `contract_clauses` (4,160), `contract_risk` (260), `contract_renewals` (260), `negotiation_history` (364) |
| `wealthpilot` | `applicants` (350), `bureau_reports` (350), `bank_statements` (1,200), `past_decisions` (220), `policy_limits` (11), `risk_grades` (8), `approval_authorities` (3), `sector_policies` (8), `reason_codes` (15), `reference_rates` (7), `signatories` (20), `loan_applications` (350), `underwriting_reference` (350) |
| `shopsense` | `customers` (500), `products` (600), `orders` (1,500), `shipments` (1,500), `refunds` (320), `policy_limits` (15), `category_policies` (8), `refund_authority` (5), `refund_rules` (7), `refund_processing_times` (5), `delivery_services` (6), `delay_compensation` (3), `escalation_triggers` (8), `carriers` (5), `sellers` (120), `order_fulfilment` (1,500), `goodwill_credits` (155), `replacements` (63), `customer_profiles` (500), `support_tickets` (861) |
| `plantguard` | `assets` (28), `asset_classes` (8), `criticality_matrix` (3), `asset_criticality` (28), `telemetry` (20,160), `telemetry_pressure` (8,640), `work_orders` (400), `work_order_details` (400), `technicians` (40), `technician_calendar` (1,120), `inventory` (280), `suppliers` (12), `part_suppliers` (280), `purchase_orders` (117) |

Column-level schemas for every table, and how the tables join, are in [`capstone-data-toolkit/README.md`](capstone-data-toolkit/README.md#data-reference).

### PlantGuard: which table backs which tool

| You are building | Read these tables |
|---|---|
| Sensor-history API (M2) | `telemetry`, `telemetry_pressure`, with alarm limits from `asset_classes` |
| Downtime-cost calculator (M2) | `asset_criticality` for the asset's hourly rate, `criticality_matrix` for the class rules, `work_orders` for downtime minutes |
| Spare-parts inventory API (M2) | `inventory`, `part_suppliers` |
| Technician-scheduling calendar (M2) | `technicians` for skills and certifications, `technician_calendar` for free hours per day, `work_order_details` for what is already booked |
| Maintenance history memory (M3) | `work_orders` joined to `work_order_details` |
| Inventory / ERP MCP server (M6) | `inventory`, `suppliers`, `part_suppliers`, `purchase_orders` |

### CareFlow, LexOps, WealthPilot, ShopSense: which table backs which tool

**CareFlow**

| You are building | Read these tables |
|---|---|
| Patient lookup and insurance-eligibility API (M2) | `patients`, `plans` |
| Appointment-slot finder (M2) | `appointment_slots`, `providers`, `sites`, with `specialties` for the consultation length |
| Co-pay calculator (M2) | `procedures`, `plan_copays`, `plans`, and `patients.deductible_met_usd` |
| Pre-authorisation check (M2, M5) | `preauth_rules`, `referral_details` |
| Referral tracking and SLA (M5) | `referrals`, `referral_details`, `urgency_bands` |
| Per-patient memory (M3) | `patient_interactions`, `appointments` |
| Scheduling / EHR MCP server (M6) | `appointment_slots`, `appointments`, `providers`, `patients` |

**LexOps**

| You are building | Read these tables |
|---|---|
| Clause extraction and comparison against the playbook (M2, M4) | `playbook_positions`, `clause_families` |
| Risk-scoring calculator (M2) | `contract_clauses` for the points, `contract_risk` for the answer, `clause_families` for the caps |
| Approval routing (M5) | `approval_tiers`, `contract_risk` |
| Contract repository and renewal tracking (M2) | `contracts`, `contract_renewals` |
| E-signature status (M2, M6) | `signature_requests` |
| Per-counterparty memory (M3) | `negotiation_history`, `counterparties` |

**WealthPilot**

| You are building | Read these tables |
|---|---|
| DSCR and ratio calculator (M2) | `loan_applications`, `applicants`, `policy_limits`, `sector_policies`; check your answer against `underwriting_reference` |
| Credit-bureau lookup (M2) | `bureau_reports` |
| Bank-statement analysis (M2) | `bank_statements` |
| FX conversion (M2) | `reference_rates`, for `loan_applications.export_receivables_usd` |
| Risk grading and pricing (M2, M5) | `risk_grades`, `reference_rates` |
| Approval routing and human sign-off (M5, M8) | `approval_authorities`, `signatories`, `underwriting_reference` |
| Adverse-action reasons (M5) | `reason_codes` |
| Per-applicant memory (M3) | `past_decisions` |

**ShopSense**

| You are building | Read these tables |
|---|---|
| Order-lookup API (M2) | `orders`, `products`, `customers`, `order_fulfilment` |
| Shipping tracker (M2) | `shipments`, `carriers`, `order_fulfilment`, `delivery_services` |
| Refund / replace API (M2) | `refunds`, `replacements`, `goodwill_credits` |
| Refund-amount calculator (M2) | `refund_rules`, `category_policies`, `refund_processing_times`, and `orders.order_value_inr` as the amount paid |
| Per-customer memory (M3) | `support_tickets`, `customer_profiles` |
| Routing and human approval (M5) | `escalation_triggers`, `refund_authority`, `customer_profiles.automated_refunds_allowed` |
| Guardrails on automated refunds (M8) | `policy_limits`, `refund_authority` |
| Order / refund / shipping MCP server (M6) | `orders`, `shipments`, `refunds`, `replacements` |

Joins, worked examples and column notes for each are in [`capstone-data-toolkit/README.md`](capstone-data-toolkit/README.md#data-reference).

---

## Check your data

A run can stop early: a rate limit, a document the provider refuses, a table added in a newer version. Run the validator before you build on the data. It reads the files under `data/<your-domain>/`, needs no API key, and changes nothing.

### PlantGuard

```bash
python -m tests.validate_data --domain plantguard
```

A complete PlantGuard dataset has all of the following. The validator checks each line:

| Asset | What a complete dataset has | It fails when |
|---|---|---|
| Corpus | 13 documents, each as `.md` and `.pdf`, all listed in `corpus/index.json` | a document or PDF is missing, empty or unreadable |
| Intake | 200 records, each with a unique `record_id`, 7 record fields and a `ground_truth` object with 5 fields | the file is missing, a line is not JSON, or IDs repeat |
| Mock API tables | 14 tables, 120 columns, 31,516 rows, each as CSV and JSON | a table or column is missing, a value has the wrong type, an ID points at nothing, or the CSV and JSON copies disagree |
| Eval set | 20 cases with 7 fields each, including the 5 hand-written cases `PLANTGUARD-EV-901` to `PLANTGUARD-EV-905` | a field or a hand-written case is missing |
| Manifest | `manifest.json` describing the run | it is missing or unreadable |

PlantGuard gets five more checks on top, because its documents and tables must agree:

- every asset's criticality follows from its safety risk, environmental impact and downtime cost;
- every work order's technician exists in `technicians`;
- intake events name machines that exist in `assets`;
- equipment manuals cite part numbers that exist in `inventory`;
- the maintenance planning document states the criticality matrix.

The output looks like this (shortened):

```
  corpus
    [PASS] all 13 documents present as markdown and PDF
    [PASS] index.json lists all 13 documents

  tables
    [PASS] all 14 tables present as CSV and JSON
    [PASS] columns match the schema in all 14 tables (120 columns)
    [PASS] every ID that refers to another table resolves
    [PASS] values identical to a fresh build (seed 42, default mode)

  plantguard
    [WARN] 33 of 200 intake events name an asset_tag that is not in the assets table
           fix: python generate.py --domain plantguard --only intake --no-resume

  21 passed, 4 warnings, 0 failed

READY, with 4 warning(s) to read.
```

How to read it:

| Result | Meaning | What to do |
|---|---|---|
| `PASS` | As expected | Nothing |
| `NOTE` | A known limit of an original table in default mode, for example a refund larger than its order. Not a fault. | Use the table named on the `use:` line instead |
| `WARN` | Usable, but not what a fresh run of this version produces. Typical cause: data generated by an older version. | Read it, then run the `fix:` command or accept the difference |
| `FAIL` | Missing or malformed | Run the `fix:` command, then validate again |

The last line is `READY` when nothing failed, and `NOT READY` otherwise. The exit status is 1 on `NOT READY`, so the command also works in CI.

### All other problem statements

The same command works for every domain, one at a time or together:

```bash
python -m tests.validate_data --domain careflow
python -m tests.validate_data --domain all        # every domain, with a summary at the end
```

What a complete dataset has, per problem statement:

| `--domain` | Corpus documents | Intake fields (record + `ground_truth`) | Tables | Columns | Rows | Hand-written eval cases |
|---|---|---|---|---|---|---|
| `plantguard` | 13 | 7 + 5 | 14 | 120 | 31,516 | `PLANTGUARD-EV-901` to `-905` |
| `careflow` | 14 | 5 + 4 | 14 | 88 | 3,206 | `CAREFLOW-EV-901` to `-907` |
| `lexops` | 19 | 10 + 4 | 10 | 80 | 5,531 | `LEXOPS-EV-901` to `-906` |
| `wealthpilot` | 13 | 11 + 5 | 13 | 98 | 2,892 | `WEALTHPILOT-EV-901` to `-910` |
| `shopsense` | 14 | 6 + 7 | 20 | 136 | 7,681 | `SHOPSENSE-EV-901` to `-910` |

Every domain defaults to 200 intake records and 20 eval cases. Row counts are for the default seed. To list the exact documents, fields and columns behind these numbers, run `python generate.py --domain <your-domain> --schema`.

Each of these four domains also gets checks that its documents, tables and intake records agree:

| `--domain` | Extra checks |
|---|---|
| `careflow` | The cost-share schedule covers every plan; the pre-authorisation matrix names the procedures in `procedures`; every referral agrees with the rule for its procedure and plan; intake messages name registered patients |
| `lexops` | Every risk score equals the sum of the contract's clause points; the risk-scoring document names the clause families; each playbook section names its deviation; intake requests name real counterparties |
| `wealthpilot` | Every DSCR equals EBITDA over existing plus proposed debt service; the risk grading document covers every grade; the adverse action standard names the reason codes; intake applications match `loan_applications` and their labels match the reference |
| `shopsense` | Every order agrees with the delivery promise and the delay ladder; goodwill credits respect the cap and the no-stacking rule; replacements and ticketed refunds were decided at the right tier; no past ticket was handled automatically despite an escalation trigger; category addenda state the return window and restocking fee; the refund matrix states every threshold; intake tickets name real orders and customers |

The original tables of these four domains are kept exactly as v1.0.0 wrote them, so some of their rows contradict the policy (a refund above its order value, an appointment with a provider of another specialty). The validator lists each as a `NOTE` and names the table to use instead. `--fresh-table-rng` removes them; see Q13.

### Options

| Option | Use it when |
|---|---|
| `--only corpus,intake,tables,eval,manifest` | You generated only some stages and want to check just those |
| `--intake N`, `--eval-items N`, `--corpus-docs N` | You generated a smaller set on purpose, for example `--corpus-docs 4 --intake 20` |
| `--data <folder>` | Your data is not in `./data` |
| `--strict` | Warnings should count as failures, for example in CI |

### Two test commands, two purposes

| Command | Checks | Run it |
|---|---|---|
| `python -m tests.validate_data --domain <your-domain>` | The **data** you generated | After every `generate.py` run |
| `python -m tests.test_regressions` | The **toolkit code** itself, offline, with a fake provider | After you edit a file in `datagen/` |

---

## Useful commands

```bash
# Iterate cheaply while your schema is still changing
python generate.py --domain lexops --corpus-docs 4 --intake 20 --eval-items 6

# Regenerate one stage only
python generate.py --domain wealthpilot --only eval

# Switch provider if you hit a rate limit
python generate.py --domain careflow --provider ollama

# Force a full rebuild (by default, finished documents are skipped)
python generate.py --domain careflow --no-resume

# List everything a full run produces: documents, fields, tables, columns, types
python generate.py --domain plantguard --schema

# Check that your generated data is complete and correctly shaped
python -m tests.validate_data --domain plantguard

# Run the offline test suite after changing a domain file
python -m tests.test_regressions
```

Stages for `--only`: `corpus`, `intake`, `tables`, `eval`. Combine with commas.

---

## Troubleshooting

**Q1. I get `ModuleNotFoundError: No module named 'datagen'`.**
You are in the repository root. Run `cd capstone-data-toolkit` first.

**Q2. Every LLM call fails with a 404 error.**
Your model has been retired. Set `DATAGEN_GEMINI_MODEL=gemini-flash-latest` in `.env` (see step 4).

**Q3. It says "No Gemini key" even though I created `.env`.**
Your `.env` is in the wrong folder. It must be inside `capstone-data-toolkit/`, next to `generate.py`.

**Q4. The run stopped halfway.**
Run the same command again. Finished corpus documents, intake records and eval sets are kept, so you only pay for what is missing. Then run `python -m tests.validate_data --domain <your-domain>` to confirm nothing is left out.

**Q5. A document was reported as "blocked".**
The provider's safety filter refused it. This is common for clinical (CareFlow) and hazardous-procedure (PlantGuard) documents. Everything else still generated. Write that one document by hand, or retry with `--provider ollama`.

**Q6. I got fewer intake records than I asked for.**
The generator stops instead of looping forever when the model returns empty batches. Run again to top up.

**Q7. My eval set printed a distribution warning.**
The model ignored the requested category mix, for example returning mostly factual questions. Re-run with `--only eval`, or add the missing categories by hand.

**Q8. I'm rate-limited on the free tier.**
Wait and re-run (progress is kept), or switch with `--provider openrouter` or `--provider ollama`. Ollama runs locally with no key and no limit.

**Q9. I used an earlier version. Do I need to regenerate?**
Your existing mock API tables are byte-identical in v1.0.4, so nothing you built breaks. Three steps bring everything else up to date:

```bash
python generate.py --domain <your-domain> --only tables              # adds the new tables; no API key
python generate.py --domain <your-domain> --only corpus --no-resume  # documents that state the same figures as the tables
python generate.py --domain <your-domain> --only intake,eval --no-resume
```

The first step is free and safe for everyone. The other two use your API quota: the documents written before v1.0.4 carry figures the model invented (a restocking fee, a co-pay, a DSCR floor) that no table agrees with, the old intake records name patients, applicants and orders that do not exist, and the old eval answers were not checked against the corpus. `python -m tests.validate_data --domain <your-domain>` tells you which of these apply to your data. See `CHANGELOG.md` for the full list.

**Q10. I get `ModuleNotFoundError: No module named 'pydantic_core'` (or another missing package).**
Your virtual environment is only half installed. This happens when an install is interrupted, or when packages were installed by a different Python than the one now running. With the virtual environment activated, run:

```bash
python -m pip install --force-reinstall --no-cache-dir -r requirements.txt
```

Use `python -m pip`, not bare `pip`, so the packages go into the Python that runs `generate.py`. If it still fails, rebuild the environment: `deactivate`, then `python -m venv --clear .venv`, activate it again, and `python -m pip install -r requirements.txt`. From v1.0.3 the toolkit prints these steps itself instead of a traceback.

**Q11. PlantGuard: where are the safety risk, environmental impact and downtime cost behind criticality A/B/C?**
In `mock_api/criticality_matrix` (the class rules) and `mock_api/asset_criticality` (each asset's own three factors and its hourly downtime cost in rupees). An asset takes the most severe class indicated by any one factor.

**Q12. PlantGuard: where are the technicians and their skills?**
In `mock_api/technicians` (40 people, each with a trade, level and permit certifications) and `mock_api/technician_calendar` (their shift and free hours for 28 days). Every `technician_id` in `work_orders` resolves to a row in `technicians`.

**Q13. The validator prints `NOTE` lines. Is my data broken?**
No. A `NOTE` is a known limit of a table that existed before v1.0.4. Those tables drew every column independently, so, for example, 126 ShopSense refunds exceed their order value and 795 CareFlow appointments pair a provider with another specialty. They are left as they are so that teams who already built on them see no change. Each `NOTE` names the table that holds the correct answer. If you are starting fresh, generate with `--fresh-table-rng` instead: the original tables are then made consistent too. Decide once per team, because the two modes produce different rows.

**Q14. A figure in a policy document disagrees with a mock API table.**
From v1.0.4 both come from the same source, so this means the document was generated by an older version or the model ignored the figure it was given. The table is right. Run the validator: it names the document, and `python generate.py --domain <your-domain> --only corpus --no-resume` rewrites it.

**Q15. My eval set has fewer cases than I asked for.**
Cases whose expected answer could not be found in the corpus were discarded rather than kept as wrong answers. Run `python generate.py --domain <your-domain> --only eval` again to top up. If it keeps happening, check that the corpus is complete first.

---

## Ground rules

- **No real personal data. Ever.** No real patient records, loan applicants, or customer PII, even if a dataset is public or anonymised.
- **Check licences before reusing public datasets.** Several recommended datasets are non-commercial. That's fine for coursework but not for a product.
- **Never commit `.env` or your `data/` folder.** Your key lives in one; the other is regenerable and large.

---

## Learn more

- `capstone-data-toolkit/README.md`: full toolkit reference and design decisions
- `CHANGELOG.md`: what changed between versions and why
- **Data Sourcing Guide**: public datasets and synthetic-data strategy for each problem statement
