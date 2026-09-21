# Project Data Toolkit

**Applied AI Professional Certification Program · IIT Hyderabad**

This repository generates the data you need for your project. You pick your problem statement, run one command, and get four ready-to-use data assets: a document corpus for RAG, raw intake records, mock API tables, and a golden evaluation set.

You do not need to invent data from scratch. Read the **Data Sourcing Guide** alongside this repo. It tells you which public datasets to use for your problem statement, and this toolkit generates the parts nobody publishes.

---

## Find your domain

Every command takes a `--domain` flag. Use the one that matches your problem statement.

| Problem statement | `--domain` | Corpus docs | Mock API tables |
|---|---|---|---|
| CareFlow: AI Care Coordination Assistant | `careflow` | 14 | plans, patients, appointments, referrals |
| LexOps: Contract Intelligence & Compliance Copilot | `lexops` | 19 | counterparties, contracts, signature_requests |
| WealthPilot: SME Loan Underwriting Assistant | `wealthpilot` | 13 | applicants, bureau_reports, bank_statements, past_decisions |
| ShopSense: Customer Care & Order Operations | `shopsense` | 14 | customers, products, orders, shipments, refunds |
| PlantGuard: Predictive Maintenance Copilot | `plantguard` | 13 | assets, telemetry, work_orders, inventory |

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
        ├── stub_provider.py     ← fake LLM, so tests need no API key
        └── test_regressions.py  ← offline test suite
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
pip install -r requirements.txt
```

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
Run the same command again. Finished corpus documents are skipped, so you only pay for what is missing.

**Q5. A document was reported as "blocked".**
The provider's safety filter refused it. This is common for clinical (CareFlow) and hazardous-procedure (PlantGuard) documents. Everything else still generated. Write that one document by hand, or retry with `--provider ollama`.

**Q6. I got fewer intake records than I asked for.**
The generator stops instead of looping forever when the model returns empty batches. Run again to top up.

**Q7. My eval set printed a distribution warning.**
The model ignored the requested category mix, for example returning mostly factual questions. Re-run with `--only eval`, or add the missing categories by hand.

**Q8. I'm rate-limited on the free tier.**
Wait and re-run (progress is kept), or switch with `--provider openrouter` or `--provider ollama`. Ollama runs locally with no key and no limit.

**Q9. I used v1.0.0. Do I need to regenerate?**
No. Your mock API tables are byte-identical in v1.0.1. Run `python generate.py --domain <your-domain> --only tables` once to get the `manifest.json` that v1.0.0 never wrote. See `CHANGELOG.md` for the full list of fixes.

---

## Ground rules

- **No real personal data. Ever.** No real patient records, loan applicants, or customer PII, even if a dataset is public or anonymised.
- **Check licences before reusing public datasets.** Several recommended datasets are non-commercial. That's fine for coursework but not for a product.
- **Never commit `.env` or your `data/` folder.** Your key lives in one; the other is regenerable and large.

---

## Learn more

- `capstone-data-toolkit/README.md`: full toolkit reference and design decisions
- `CHANGELOG.md`: what changed between versions and why
- **Capstone Data Sourcing Guide**: public datasets and synthetic-data strategy for each problem statement
