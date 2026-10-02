# Capstone Data Toolkit

**v1.0.4** — see `CHANGELOG.md`. If you generated data with an earlier version,
your existing mock API tables are unchanged. Every domain gains the tables its
problem statement needs and never had (51 in all: 10 for PlantGuard in v1.0.3,
then 10 for CareFlow, 7 for LexOps, 9 for WealthPilot and 15 for ShopSense);
run `--only tables` once to add them. Documents, intake records and eval
answers are now built from the same figures as the tables.

Generates the four data assets every capstone in the Applied AI Professional
Certification Program needs, for all five problem statements.

| Asset | Feeds | What it is |
|---|---|---|
| **A. RAG corpus** | M3, M4 | Policy/playbook/manual documents, in markdown *and* PDF |
| **B. Intake records** | M1 | Raw messy inputs to parse into Pydantic objects |
| **C. Mock API tables** | M2, M6 | Relational seed data behind your tools and MCP server |
| **D. Golden eval set** | M8 | 20 graded cases, adversarial ones included |

## Quickstart

```bash
python -m pip install -r requirements.txt
cp .env.example .env          # add your Gemini key
python generate.py --domain shopsense --dry-run    # see the plan, spend nothing
python generate.py --domain shopsense              # generate everything
```

Domains: `careflow`, `lexops`, `wealthpilot`, `shopsense`, `plantguard`, `all`.

**No API key yet?** The mock API tables need no LLM at all:

```bash
python generate.py --domain plantguard --only tables
```

That gets you a working M2 in minutes while you sort out credentials.

## Useful invocations

```bash
# Iterate fast on a small corpus before committing to a full run
python generate.py --domain lexops --corpus-docs 4 --intake 20 --eval-items 6

# A crashed run resumes; completed documents are skipped
python generate.py --domain careflow

# Rate-limited on Gemini? Switch provider, keep everything else
python generate.py --domain careflow --provider ollama

# Regenerate one stage only
python generate.py --domain wealthpilot --only eval
```

## Output layout

```
data/<domain>/
  corpus/
    markdown/*.md        clean-parse baseline
    pdf/*.pdf            the messy real case -- chunk this too
    index.json
  intake/records.jsonl   each record carries a ground_truth block
  mock_api/*.csv|json    seed tables for your tools
  eval/golden_set.json   20 cases with categories and expected routes
  manifest.json          provenance, seed, licences
```

## Data reference

What each run produces, table by table. To print it from the code itself,
together with the corpus document list and the intake and eval fields (no API
key, nothing written):

```bash
python generate.py --domain <domain> --schema
```

Conventions for every mock API table:

- Written twice, as `mock_api/<table>.csv` and `mock_api/<table>.json`.
- An empty value is blank in CSV and `null` in JSON. "nullable" below marks
  the columns where that happens.
- Dates and date-times are ISO strings. They are anchored to a frozen "today"
  of **2026-08-01 09:00**, not the wall clock, so treat that as "now".
- Row counts are for the default seed (42). Columns never change with the seed.

The corpus index, intake record and eval case schemas are the same shape in
every domain and are described in the repository's top-level `README.md`.

### PlantGuard (`plantguard`)

Fourteen tables. The first four existed in v1.0.0 and are byte-identical; the
other ten were added in v1.0.3.

| You are building | Read these tables |
|---|---|
| Sensor-history API (M2) | `telemetry`, `telemetry_pressure`, limits from `asset_classes` |
| Downtime-cost calculator (M2) | `asset_criticality`, `criticality_matrix`, `work_orders` |
| Spare-parts inventory API (M2) | `inventory`, `part_suppliers` |
| Technician-scheduling calendar (M2) | `technicians`, `technician_calendar`, `work_order_details` |
| Maintenance history memory (M3) | `work_orders` + `work_order_details` |
| Inventory / ERP MCP server (M6) | `inventory`, `suppliers`, `part_suppliers`, `purchase_orders` |

How the tables join:

```
asset_classes.asset_code ──< assets.asset_code          inventory.asset_code >── asset_classes
assets.asset_tag ──1 asset_criticality.asset_tag        criticality_matrix.criticality ──< assets.criticality
assets.asset_tag ──< telemetry / telemetry_pressure / work_orders
work_orders.work_order_id ──1 work_order_details        work_orders.technician_id >── technicians
technicians.technician_id ──< technician_calendar       work_order_details.part_number >── inventory
inventory.part_number ──1 part_suppliers >── suppliers  purchase_orders >── inventory, suppliers
```

Two worked examples:

- **Downtime cost of a stoppage.** Look up the asset in `asset_criticality`
  and multiply `downtime_cost_per_hour_inr` by the hours lost. If you know only
  the class, use `default_downtime_cost_inr_per_hour` from `criticality_matrix`.
- **Who can do an Electrical job of 4 hours on 2026-08-05?** Take
  `technicians` whose `primary_skill` or `secondary_skill` is `Electrical`,
  join `technician_calendar` on that `date`, and keep rows with
  `status = on_shift` and `available_hours >= 4`. Add a certification filter
  (for example `high_voltage_certified`) if the job needs a permit.

#### Asset registry and criticality

**`assets`** — 28 rows. Key: `asset_tag`. Asset registry: one row per machine.

| Column | Type | Meaning |
|---|---|---|
| `asset_tag` | str | Unique machine ID, e.g. `VPW-HYD-PRESS-02` |
| `asset_code` | str | Asset class: `CNC-MILL`, `HYD-PRESS`, `CONV-BELT`, `AIR-COMP`, `IND-OVEN`, `PUMP-CENT`, `ROBOT-WELD`, `CHILLER`. Joins to `asset_classes` |
| `description` | str | Class name, e.g. "400-Tonne Hydraulic Press" |
| `criticality` | str | `A`, `B` or `C`. The factors behind it are in `asset_criticality` |
| `installed_on` | str | Date installed |
| `running_hours` | int | Total running hours |
| `line` | str | Production line, `LINE-1` to `LINE-4` |
| `last_pm_on` | str | Date of the last preventive maintenance |

**`asset_classes`** — 8 rows. Key: `asset_code`. One row per asset class: alarm limits and responsible trade. The equipment manuals are generated from these same figures.

| Column | Type | Meaning |
|---|---|---|
| `asset_code` | str | Asset class |
| `description` | str | Class name |
| `primary_skill` | str | Trade that normally works on this class |
| `secondary_skill` | str | Supporting trade |
| `vibration_warning_mm_s` | float | Vibration warning limit, mm/s RMS |
| `vibration_trip_mm_s` | float | Vibration trip limit |
| `temp_warning_c` | int | Surface temperature warning limit, °C |
| `temp_trip_c` | int | Surface temperature trip limit |
| `pm_interval_hours` | int | Base preventive maintenance interval, running hours |
| `energy_sources` | str | Hazardous energy to isolate under lockout/tagout, `;`-separated |
| `pressure_nominal_bar` | float, nullable | Normal operating pressure. Empty for classes with no monitored pressure |
| `pressure_low_alarm_bar` | float, nullable | Low-pressure alarm limit. Empty for the same classes |

**`criticality_matrix`** — 3 rows. Key: `criticality`. The Reliability Committee's rules for class A/B/C (maintenance-planning clause 2.1). An asset takes the **most severe** class indicated by any one factor.

| Column | Type | Meaning |
|---|---|---|
| `criticality` | str | `A`, `B` or `C` |
| `safety_risk` | str | Safety risk at this class: `HIGH`, `MEDIUM`, `LOW` |
| `environmental_impact` | str | Environmental impact at this class: `CRITICAL`, `MAJOR`, `MINOR` |
| `downtime_cost_min_inr_per_hour` | int | Lower bound of the downtime-cost band, rupees per hour |
| `downtime_cost_max_inr_per_hour` | int, nullable | Upper bound. Empty for class A (no ceiling) |
| `default_downtime_cost_inr_per_hour` | int | Rate to use when you know only the class, not the asset |
| `inspection_interval_days` | int | Inspection interval for the class |

**`asset_criticality`** — 28 rows. Key: `asset_tag`. Each asset's own three factors and hourly downtime cost. This is the input to the downtime-cost calculator.

| Column | Type | Meaning |
|---|---|---|
| `asset_tag` | str | Joins to `assets` |
| `criticality` | str | Same value as `assets.criticality` |
| `safety_risk` | str | `HIGH`, `MEDIUM` or `LOW` for this asset |
| `environmental_impact` | str | `CRITICAL`, `MAJOR` or `MINOR` for this asset |
| `downtime_cost_per_hour_inr` | int | This asset's production downtime cost, rupees per hour |
| `governing_factor` | str | Which factor(s) put the asset in its class, `;`-separated: `safety_risk`, `environmental_impact`, `downtime_cost` |

#### Sensor history

**`telemetry`** — 20,160 rows. Key: `asset_tag` + `hour_index`. Hourly sensor history, 720 rows (30 days) per asset. About a fifth of assets carry a slowly accelerating seeded fault.

| Column | Type | Meaning |
|---|---|---|
| `asset_tag` | str | Joins to `assets` |
| `hour_index` | int | Hour 0 to 719, oldest first |
| `vibration_mm_s` | float | Vibration, mm/s RMS |
| `temp_c` | float | Surface temperature, °C |
| `current_a` | float | Motor current, A |
| `seeded_fault` | bool | Ground truth: true once the seeded fault has started. Do not show this to your model |

**`telemetry_pressure`** — 8,640 rows. Key: `asset_tag` + `hour_index`. Hourly pressure history for the four classes that have a pressure system (`HYD-PRESS`, `AIR-COMP`, `PUMP-CENT`, `CHILLER`). Join to `telemetry` on both key columns.

| Column | Type | Meaning |
|---|---|---|
| `asset_tag` | str | Joins to `assets` |
| `hour_index` | int | Same hour index as `telemetry` |
| `pressure_bar` | float | Operating pressure, bar. Falls slowly once a seeded fault starts |

#### Work orders, technicians and scheduling

**`work_orders`** — 400 rows. Key: `work_order_id`. Maintenance work orders, past and current.

| Column | Type | Meaning |
|---|---|---|
| `work_order_id` | str | Unique ID, e.g. `VPW-WO-00042` |
| `asset_tag` | str | Joins to `assets` |
| `raised_on` | str | Date raised |
| `type` | str | `preventive`, `corrective`, `predictive`, `breakdown` |
| `priority` | str | `P1` (highest) to `P4` |
| `status` | str | `open`, `in_progress`, `deferred`, `closed` |
| `downtime_minutes` | int | Production downtime caused, minutes |
| `permit_required` | bool | True if the job needs a permit to work |
| `technician_id` | str | Assigned technician. Joins to `technicians` |

**`work_order_details`** — 400 rows. Key: `work_order_id`. One row per work order: what the job needs, when it is scheduled, and what it cost.

| Column | Type | Meaning |
|---|---|---|
| `work_order_id` | str | Joins to `work_orders` |
| `required_skill` | str | Trade the job needs. The assigned technician holds it |
| `estimated_hours` | int | Planned labour hours |
| `scheduled_date` | str, nullable | Planned date for open, in-progress and deferred jobs. Empty for closed jobs |
| `scheduled_shift` | str, nullable | Shift of the planned date: `A`, `B` or `C` |
| `completed_on` | str, nullable | Completion date for closed jobs. Empty otherwise |
| `actual_hours` | float, nullable | Labour hours actually used. Closed jobs only |
| `failure_mode` | str, nullable | What failed, e.g. `bearing_wear`, `seal_leak`, `sensor_fault`. Empty for preventive jobs |
| `permit_type` | str, nullable | `hot_work`, `confined_space`, `work_at_height`, `high_voltage`, `pressure_system`. Empty when no permit is required |
| `part_number` | str, nullable | Spare part used or reserved. Joins to `inventory`. May be empty |
| `part_quantity` | int | Units of that part (0 when none) |
| `downtime_cost_inr` | int | `downtime_minutes` ÷ 60 × the asset's `downtime_cost_per_hour_inr` |

**`technicians`** — 40 rows. Key: `technician_id`. The maintenance crew. Every `technician_id` in `work_orders` is here.

| Column | Type | Meaning |
|---|---|---|
| `technician_id` | str | `VPW-T-001` to `VPW-T-040` |
| `name` | str | Invented name |
| `primary_skill` | str | Main trade: `Mechanical`, `Electrical`, `Instrumentation`, `Hydraulics`, `Robotics` |
| `secondary_skill` | str, nullable | Second trade, if any |
| `skill_level` | str | `L1` trainee, `L2` technician, `L3` senior |
| `years_experience` | int | Years in the trade |
| `base_shift` | str | Shift in the first week: `A`, `B` or `C`. Shifts rotate weekly |
| `home_line` | str | Usual production line |
| `loto_authorised` | bool | May apply and remove lockout/tagout locks |
| `hot_work_certified` | bool | Holds the hot-work permit certification |
| `confined_space_certified` | bool | Holds the confined-space certification |
| `work_at_height_certified` | bool | Holds the work-at-height certification |
| `high_voltage_certified` | bool | Holds the high-voltage certification |
| `pressure_system_certified` | bool | Holds the pressure-system certification |
| `hourly_rate_inr` | int | Labour cost, rupees per hour |

**`technician_calendar`** — 1,120 rows. Key: `technician_id` + `date`. The scheduling calendar: one row per technician per day for 28 days from 2026-08-01.

| Column | Type | Meaning |
|---|---|---|
| `technician_id` | str | Joins to `technicians` |
| `date` | str | Calendar date |
| `shift` | str | `A` 06:00–14:00, `B` 14:00–22:00, `C` 22:00–06:00 |
| `shift_start` | str | Shift start, local date-time |
| `shift_end` | str | Shift end (next day for shift C) |
| `status` | str | `on_shift`, `rest_day`, `leave`, `training` |
| `booked_hours` | int | Hours already committed to scheduled work orders that day |
| `available_hours` | int | Hours still free. 0 unless `on_shift` |

#### Inventory and purchasing

**`inventory`** — 280 rows. Key: `part_number`. Spare-parts stock.

| Column | Type | Meaning |
|---|---|---|
| `part_number` | str | Unique ID, e.g. `VPW-P-00123`. The equipment manuals cite these |
| `description` | str | Part description |
| `asset_code` | str | Asset class the part fits |
| `on_hand` | int | Units in stock |
| `reorder_point` | int | Reorder when `on_hand` is at or below this |
| `unit_cost_inr` | int | Cost per unit, rupees |
| `lead_time_days` | int | Supplier lead time |
| `supplier_tier` | str | `T1`, `T2` or `T3` |
| `criticality` | str | Part criticality `A`/`B`/`C` (drives minimum stock) |

**`suppliers`** — 12 rows. Key: `supplier_id`. Approved suppliers, four per tier.

| Column | Type | Meaning |
|---|---|---|
| `supplier_id` | str | `VPW-SUP-001` to `VPW-SUP-012` |
| `supplier_name` | str | Invented company name |
| `tier` | str | `T1` OEM or authorised distributor, `T2` approved alternate, `T3` local or spot supplier |
| `city` | str | Supplier location |
| `payment_terms_days` | int | Payment terms |
| `on_time_delivery_pct` | int | Historical on-time delivery, percent |
| `status` | str | `approved` or `probation` |

**`part_suppliers`** — 280 rows. Key: `part_number`. Which supplier quotes each part: one row per part.

| Column | Type | Meaning |
|---|---|---|
| `part_number` | str | Joins to `inventory` |
| `supplier_id` | str | Joins to `suppliers`. Its tier equals `inventory.supplier_tier` |
| `quoted_lead_time_days` | int | Same as `inventory.lead_time_days` |
| `unit_price_inr` | int | Same as `inventory.unit_cost_inr` |
| `min_order_quantity` | int | Smallest quantity the supplier accepts |

**`purchase_orders`** — 117 rows. Key: `po_id`. Open and historical purchase orders. Some low-stock parts (16 of 63 at the default seed) have **no** open order: that is the gap your procurement agent fills.

| Column | Type | Meaning |
|---|---|---|
| `po_id` | str | Unique ID, e.g. `VPW-PO-00017` |
| `part_number` | str | Joins to `inventory` |
| `supplier_id` | str | Joins to `suppliers` |
| `quantity` | int | Units ordered |
| `unit_cost_inr` | int | Cost per unit |
| `total_inr` | int | `quantity` × `unit_cost_inr` |
| `raised_on` | str | Date raised |
| `expected_delivery_on` | str | `raised_on` + lead time |
| `received_on` | str, nullable | Date received. Empty until then |
| `status` | str | `pending_approval`, `approved`, `in_transit`, `received`, `cancelled` |
| `raised_by` | str | `auto_reorder` or `planner`. Never `auto_reorder` above ₹200,000 |
| `approval_tier` | str | `auto` (up to ₹200,000), `maintenance_manager` (up to ₹1,000,000), `plant_head` (above) |
| `approved_by` | str, nullable | `system`, `maintenance_planner`, `maintenance_manager` or `plant_head`. Empty while pending or if cancelled |

Limits to know about:

- `telemetry` has no pressure column; pressure is in `telemetry_pressure`
  because the original table is kept byte-identical.
- The four original tables still draw each column independently. An open work
  order can have an old `raised_on`, and `inventory.lead_time_days` does not
  depend on `supplier_tier`. The ten new tables are consistent with each
  other and with the originals.

### CareFlow (`careflow`)

Fourteen tables. The first four existed in v1.0.0 and are byte-identical; the other ten were added in v1.0.4.

| You are building | Read these tables |
|---|---|
| Patient lookup and insurance-eligibility API (M2) | `patients`, `plans` |
| Appointment-slot finder (M2) | `appointment_slots`, `providers`, `sites`, with `specialties` for the consultation length |
| Co-pay calculator (M2) | `procedures`, `plan_copays`, `plans`, and `patients.deductible_met_usd` |
| Pre-authorisation check (M2, M5) | `preauth_rules`, `referral_details` |
| Referral tracking and SLA (M5) | `referrals`, `referral_details`, `urgency_bands` |
| Per-patient memory (M3) | `patient_interactions`, `appointments` |
| Scheduling / EHR MCP server (M6) | `appointment_slots`, `appointments`, `providers`, `patients` |

How the tables join:

```
plans.plan_code ──< patients.plan_code                 plans ──< plan_copays, preauth_rules
patients.patient_ref ──< appointments, referrals, patient_interactions
patients.primary_site >── sites.site_id                providers.site_id >── sites
specialties.specialty ──< providers, procedures, appointment_slots, referrals.to_specialty
providers.provider_id ──< appointment_slots            referrals.referral_id ──1 referral_details
procedures.procedure_code ──< preauth_rules, referral_details
referral_details.assigned_provider_id >── providers    referrals.urgency >── urgency_bands
```

Worked examples:

- **What a patient owes.** Look up the procedure in `procedures`. If `cost_share_basis` is `copay`, the patient pays the flat amount in `plan_copays` for that plan and service category. If it is `deductible_then_coinsurance`, the patient pays the unmet part of the plan deductible (`plans.annual_deductible_usd` minus `patients.deductible_met_usd`, never below zero) plus `coinsurance_rate` on the rest of `list_price_usd`, capped at `out_of_pocket_max_usd`. A MERIDIAN-SILVER patient who has met $500 owes $1,480 for a colonoscopy (`GAST-COLO`, $2,600).
- **Does this referral need pre-authorisation, and by when must it be actioned?** `referral_details.procedure_code` plus the patient's `plan_code` give one row of `preauth_rules` (`covered`, `preauth_required`, `approval_window_business_days`). `referral_details.sla_due_on` is `referrals.raised_on` plus the business days for its urgency in `urgency_bands`.

| Table | Rows | Key | What it holds | Columns (type) |
|---|---|---|---|---|
| `plans` | 4 | `plan_code` | The four insurance plans: deductible, coinsurance rate, out-of-pocket maximum, consultation and telehealth co-pays. | `plan_code` (str), `plan_name` (str), `annual_deductible_usd` (int), `coinsurance_rate` (float), `out_of_pocket_max_usd` (int), `specialist_copay_usd` (int), `telehealth_copay_usd` (int) |
| `patients` | 400 | `patient_ref` | Registered patients with plan, member number, eligibility status and deductible met this year. | `patient_ref` (str), `given_name` (str), `family_name` (str), `birth_date` (str), `plan_code` (str), `member_number` (str), `eligibility_status` (str), `deductible_met_usd` (int), `primary_site` (str) |
| `appointments` | 900 | `appointment_id` | Past and booked appointments. | `appointment_id` (str), `patient_ref` (str), `specialty` (str), `provider_id` (str), `scheduled_for` (str), `status` (str), `duration_minutes` (int) |
| `referrals` | 300 | `referral_id` | Referrals between specialties with urgency, status and whether pre-authorisation is needed. | `referral_id` (str), `patient_ref` (str), `from_specialty` (str), `to_specialty` (str), `urgency` (str), `raised_on` (str), `status` (str), `preauth_required` (bool) |
| `specialties` | 8 | `specialty` | The eight specialties: procedure-code prefix, new-patient consultation length, target days to a first appointment. | `specialty` (str), `procedure_prefix` (str), `consult_duration_minutes` (int), `first_appointment_target_days` (int) |
| `urgency_bands` | 4 | `urgency` | First-response time and referral SLA for Routine, Priority, Urgent and Emergent. Emergent has no SLA: it is never referred. | `urgency` (str), `first_response_hours` (int), `referral_sla_business_days` (int, nullable) |
| `sites` | 14 | `site_id` | Clinic sites with opening hours. `patients.primary_site` points here. | `site_id` (str), `site_name` (str), `city` (str), `opens_at` (str), `closes_at` (str), `telehealth_enabled` (bool) |
| `providers` | 60 | `provider_id` | Clinicians: specialty, site, whether they take new patients or offer telehealth. | `provider_id` (str), `name` (str), `specialty` (str), `site_id` (str), `accepts_new_patients` (bool), `offers_telehealth` (bool), `years_in_practice` (int) |
| `appointment_slots` | 480 | `slot_id` | Slots for the two weeks from 2026-08-03, eight per provider, inside the site's opening hours and never overlapping. `status` is `open`, or `booked` where the provider already has an appointment then. This is what the slot finder searches. | `slot_id` (str), `provider_id` (str), `site_id` (str), `specialty` (str), `starts_at` (str), `duration_minutes` (int), `mode` (str), `status` (str) |
| `procedures` | 24 | `procedure_code` | Three services per specialty (a consultation, imaging or lab, and a procedure) with list price, duration and how the patient's share is worked out. | `procedure_code` (str), `procedure_name` (str), `specialty` (str), `category` (str), `list_price_usd` (int), `duration_minutes` (int), `cost_share_basis` (str) |
| `preauth_rules` | 96 | `procedure_code + plan_code` | For every procedure under every plan: covered or not, pre-authorisation needed or not, and the approval window. | `procedure_code` (str), `plan_code` (str), `covered` (bool), `preauth_required` (bool), `approval_window_business_days` (int, nullable) |
| `plan_copays` | 16 | `plan_code + service_category` | Flat co-pay per plan for consultation, telehealth, imaging and lab. | `plan_code` (str), `service_category` (str), `copay_usd` (int) |
| `referral_details` | 300 | `referral_id` | One row per referral: the procedure asked for, pre-authorisation status, assigned provider, SLA and due date. | `referral_id` (str), `procedure_code` (str), `preauth_status` (str), `assigned_provider_id` (str, nullable), `sla_business_days` (int), `sla_due_on` (str) |
| `patient_interactions` | 600 | `interaction_id` | Past contacts per patient (topic, outcome, one-line summary, and the referral asked about). Seed data for per-patient memory. | `interaction_id` (str), `patient_ref` (str), `occurred_at` (str), `channel` (str), `topic` (str), `outcome` (str), `summary` (str), `referral_id` (str, nullable) |

Columns worth a note:

| Column | Meaning |
|---|---|
| `procedures.cost_share_basis` | `copay` (consultation, imaging, lab) or `deductible_then_coinsurance` (procedure) |
| `preauth_rules.approval_window_business_days` | Empty when no pre-authorisation is needed or the procedure is not covered |
| `referral_details.preauth_status` | `not_required`, `pending`, `approved` or `denied`; it is `not_required` exactly when `referrals.preauth_required` is false |
| `referral_details.assigned_provider_id` | Empty until the referral is scheduled; always a provider of the referral's `to_specialty` |
| `patient_interactions.outcome` | `resolved`, `callback_scheduled`, `routed_to_billing` or `escalated_to_clinician`. Clinical questions are always escalated, never answered |
| `patient_interactions.referral_id` | Set on `referral_status` contacts: that patient's referral, asked about after it was raised. Empty otherwise |
| `providers.offers_telehealth`, `appointment_slots.mode` | Telehealth only where `sites.telehealth_enabled` is true |
| `referral_details.sla_due_on` | `raised_on` plus the SLA in business days, so an Urgent referral raised on a Friday is due on Monday |

Known limits of the original tables. They are kept exactly as v1.0.0 wrote them, the validator reports each as a `NOTE`, and `--fresh-table-rng` removes them:

- `appointments` pairs a provider with a specialty that is not theirs on 795 of 900 rows. Use `providers.specialty` and `appointment_slots` for scheduling.
- 33 patients have `deductible_met_usd` above their plan's deductible. Treat those as fully met, as the cost-share schedule says.

### LexOps (`lexops`)

Ten tables. The first three existed in v1.0.0 and are byte-identical; the other seven were added in v1.0.4.

| You are building | Read these tables |
|---|---|
| Clause extraction and comparison against the playbook (M2, M4) | `playbook_positions`, `clause_families` |
| Risk-scoring calculator (M2) | `contract_clauses` for the points, `contract_risk` for the answer, `clause_families` for the caps |
| Approval routing (M5) | `approval_tiers`, `contract_risk` |
| Contract repository and renewal tracking (M2) | `contracts`, `contract_renewals` |
| E-signature status (M2, M6) | `signature_requests` |
| Per-counterparty memory (M3) | `negotiation_history`, `counterparties` |

How the tables join:

```
counterparties.counterparty_id ──< contracts, negotiation_history
contracts.contract_id ──< contract_clauses (16 per contract), signature_requests
contracts.contract_id ──1 contract_risk, contract_renewals
playbook_positions.clause_type ──< contract_clauses, negotiation_history
clause_families.clause_family ──< playbook_positions
approval_tiers.tier ──< contract_risk.risk_band, contract_risk.approval_tier
```

Worked examples:

- **Score a contract.** Each of its 16 rows in `contract_clauses` carries `risk_points`: 0 at the preferred position, then `fallback_points`, `walk_away_points` or `deviation_points` from `playbook_positions`. The risk score is the sum, capped at 100. `contract_risk.risk_score` holds the result.
- **Who approves it?** The strictest of three tests: the score band in `approval_tiers` (Standard 0-30, Deviation 31-70, Escalation 71-100); the annual value limit of the tier (Standard up to 250,000 USD, Deviation up to 1,000,000); and any clause beyond walk-away, which goes to the role in `deviation_escalates_to`. A liability cap at anything but the preferred position needs at least Senior Counsel. So a contract can have `risk_band` Standard and `approval_tier` Deviation.

| Table | Rows | Key | What it holds | Columns (type) |
|---|---|---|---|---|
| `counterparties` | 120 | `counterparty_id` | The other side of each contract, with relationship and negotiation history count. | `counterparty_id` (str), `legal_name` (str), `jurisdiction` (str), `relationship` (str), `negotiation_rounds_to_date` (int), `historical_posture` (str) |
| `contracts` | 260 | `contract_id` | The contract repository: type, status, term, renewal settings and annual value. | `contract_id` (str), `counterparty_id` (str), `contract_type` (str), `status` (str), `effective_date` (str), `term_months` (int), `auto_renew` (bool), `renewal_notice_days` (int), `annual_value_usd` (int), `liability_cap_multiple` (float), `risk_score` (int) |
| `signature_requests` | 80 | `envelope_id` | E-signature envelopes and their status. | `envelope_id` (str), `contract_id` (str), `status` (str), `sent_at` (str), `signer_email` (str) |
| `clause_families` | 8 | `clause_family` | The eight clause families and the most risk points each can contribute. The caps add up to 100. | `clause_family` (str), `max_risk_points` (int) |
| `playbook_positions` | 16 | `clause_type` | The playbook as data: for each of 16 clause types the preferred, fallback and walk-away position, the named deviation beyond walk-away, the points for each, and the preferred clause wording. | `clause_type` (str), `title` (str), `clause_family` (str), `metric` (str), `unit` (str, nullable), `direction` (str), `preferred_value` (float/int, nullable), `fallback_value` (float/int, nullable), `walk_away_value` (float/int, nullable), `preferred_text` (str), `fallback_text` (str), `walk_away_text` (str), `named_deviation` (str), `fallback_points` (int), `walk_away_points` (int), `deviation_points` (int), `deviation_escalates_to` (str), `preferred_language` (str) |
| `approval_tiers` | 3 | `tier` | Standard, Deviation and Escalation: score range, annual value limit, approver role, whether auto-approval is allowed. | `tier` (str), `min_risk_score` (int), `max_risk_score` (int), `max_annual_value_usd` (int, nullable), `approver_role` (str), `auto_approve_allowed` (bool) |
| `contract_clauses` | 4,160 | `contract_id + clause_type` | Where every contract stands on every clause type, and the risk points that earns. | `contract_id` (str), `clause_type` (str), `position` (str), `value_number` (float/int, nullable), `value_text` (str), `risk_points` (int) |
| `contract_risk` | 260 | `contract_id` | The computed risk score, band, approval tier and approver for every contract, with its named deviations. | `contract_id` (str), `risk_score` (int), `risk_band` (str), `approval_tier` (str), `approver_role` (str), `auto_approve_allowed` (bool), `named_deviation_count` (int), `named_deviations` (str, nullable) |
| `contract_renewals` | 260 | `contract_id` | Term end, notice deadline and days left for every contract, as at 2026-08-01. | `contract_id` (str), `initial_term_end_on` (str), `current_term_end_on` (str), `notice_deadline_on` (str), `days_until_notice_deadline` (int), `renewal_status` (str) |
| `negotiation_history` | 364 | `negotiation_id` | Past negotiation rounds per counterparty: what they asked for, how Northwind responded, what was agreed and who approved it. | `negotiation_id` (str), `counterparty_id` (str), `contract_id` (str, nullable), `round_number` (int), `occurred_on` (str), `clause_type` (str), `counterparty_position` (str), `counterparty_ask` (str), `northwind_response` (str), `agreed_position` (str), `agreed_language` (str), `approved_by` (str) |

Columns worth a note:

| Column | Meaning |
|---|---|
| `playbook_positions.direction` | `higher` (a larger number is riskier), `lower` (a smaller number is riskier) or `category` (a list of acceptable values, in the `_text` columns) |
| `contract_clauses.position` | `preferred`, `fallback`, `walk_away` or `beyond_walk_away`. The last is the named deviation |
| `contract_risk.risk_band` and `approval_tier` | The band follows from the score alone; the tier also takes the annual value and named deviations into account, so it can be higher |
| `contract_renewals.renewal_status` | `upcoming`, `notice_due_soon` (deadline within 60 days), `notice_deadline_passed`, `term_ended`, or `not_in_force` for a contract that is not executed. `days_until_notice_deadline` is negative once the deadline has passed |
| `negotiation_history` | A counterparty has as many rows as `counterparties.negotiation_rounds_to_date`. A round about a contract ends at the position that contract's clause holds in `contract_clauses` (`agreed_position`), and is dated before an executed contract took effect. `contract_id` is empty where the counterparty has no contract in the repository |
| `negotiation_history.northwind_response` | `accepted` (the ask was agreed), `countered` (agreed at a better position than asked) or `escalated` (the ask was beyond walk-away) |
| `negotiation_history.approved_by` | Who approved that clause position. The contract as a whole still needs `contract_risk.approver_role` |

Known limits of the original tables. They are kept exactly as v1.0.0 wrote them, the validator reports each as a `NOTE`, and `--fresh-table-rng` removes them:

- `contracts.risk_score` is a random number from v1.0.0 and differs from `contract_risk.risk_score` on 259 of 260 contracts. Use `contract_risk`.

### WealthPilot (`wealthpilot`)

Thirteen tables. The first four existed in v1.0.0 and are byte-identical; the other nine were added in v1.0.4.

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

How the tables join:

```
applicants.applicant_id ──1 bureau_reports             applicants ──< bank_statements, past_decisions
applicants.applicant_id ──1 loan_applications ──1 underwriting_reference
applicants.sector >── sector_policies.sector
past_decisions.internal_grade >── risk_grades.grade    past_decisions.human_signatory >── signatories.user_id
past_decisions.reason_code >── reason_codes            signatories.authority >── approval_authorities
underwriting_reference.approval_authority >── approval_authorities
```

Worked examples:

- **DSCR of an application.** EBITDA (`applicants.ebitda_inr`) divided by the debt service after the loan: `loan_applications.existing_annual_debt_service_inr` plus the first-year instalments of the requested loan at the 14% assessment rate (`underwriting_reference.proposed_annual_debt_service_inr`). Compare it with the sector's `dscr_floor` in `sector_policies`.
- **Is it approvable?** Declined when DSCR is below 1.0, the bureau score is below 450, the business has operated under 24 months, or the grade is D2. Borderline when any other standard is missed: the sector DSCR floor, leverage, liquidity, a past delinquency, a revenue mismatch, a sector at its cap, a tenor longer than the grade or sector allows, collateral below the grade's cover, a figure that was not supplied, or grade C2 or D1. Otherwise approvable.
- **Can the system approve it alone?** Only if the result is `approve`, the amount is at most 1,000,000 INR and the grade is C1 or better. Otherwise, a decline included, `requires_human_signoff` is true and `approval_authority` names who signs: Credit Officer up to 1,000,000, Credit Committee up to 5,000,000, Board Credit Committee above that.

| Table | Rows | Key | What it holds | Columns (type) |
|---|---|---|---|---|
| `applicants` | 350 | `applicant_id` | Businesses applying for credit: sector, revenue, EBITDA, existing debt, months operating. | `applicant_id` (str), `business_name` (str), `sector` (str), `annual_revenue_inr` (int), `ebitda_inr` (int), `existing_debt_inr` (int), `months_operating` (int), `gst_registered` (bool), `prior_applications` (int) |
| `bureau_reports` | 350 | `applicant_id` | One credit-bureau report per applicant. | `applicant_id` (str), `bureau_score` (int), `enquiries_last_6m` (int), `active_trade_lines` (int), `dpd_30_last_12m` (int), `dpd_90_ever` (bool), `written_off_amount_inr` (int), `report_pulled_on` (str) |
| `bank_statements` | 1,200 | `statement_id` | Monthly bank statement summaries. | `statement_id` (str), `applicant_id` (str), `month` (str), `inflow_inr` (int), `outflow_inr` (int), `closing_balance_inr` (int), `bounced_instruments` (int), `avg_daily_balance_inr` (int) |
| `past_decisions` | 220 | `decision_id` | Earlier credit decisions with grade, reason code and signatory. | `decision_id` (str), `applicant_id` (str), `decided_on` (str), `outcome` (str), `internal_grade` (str), `approved_amount_inr` (int), `reason_code` (str), `human_signatory` (str) |
| `policy_limits` | 11 | `limit` | The credit policy's thresholds as rows: minimum DSCR, leverage and liquidity limits, auto-approve and signatory limits, the assessment rate. | `limit` (str), `value` (float/int), `unit` (str), `description` (str) |
| `risk_grades` | 8 | `grade` | The eight internal grades A1 to D2: minimum DSCR and bureau score, pricing spread, indicative rate, maximum tenor, collateral cover. | `grade` (str), `min_dscr` (float), `min_bureau_score` (int), `spread_bps` (int), `indicative_rate_pct` (float), `max_tenor_months` (int), `collateral_cover_pct` (int), `auto_approve_allowed` (bool) |
| `approval_authorities` | 3 | `authority` | Who may approve a loan of what size. | `authority` (str), `max_loan_inr` (int, nullable), `named_signatory_required` (bool) |
| `sector_policies` | 8 | `sector` | Per sector: DSCR floor, working-capital cycle, exposure cap and current exposure, maximum tenor, seasonal peak. | `sector` (str), `dscr_floor` (float), `working_capital_cycle_days` (int), `max_exposure_pct` (float), `current_exposure_pct` (float), `at_sector_cap` (bool), `max_tenor_months` (int), `seasonal_peak` (str) |
| `reason_codes` | 15 | `reason_code` | The fifteen decision reason codes and whether each is a reason to decline or refer. | `reason_code` (str), `meaning` (str), `is_decline_reason` (bool) |
| `reference_rates` | 7 | `rate` | Base rate, assessment rate and five FX rates to INR, as at 2026-08-01. | `rate` (str), `value` (float), `as_of` (str) |
| `signatories` | 20 | `user_id` | The people who can sign a decision, with their authority and limit. | `user_id` (str), `name` (str), `authority` (str), `approval_limit_inr` (int, nullable), `active` (bool) |
| `loan_applications` | 350 | `application_id` | One live application per applicant: amount, tenor, purpose, the figures the applicant declared, collateral. | `application_id` (str), `applicant_id` (str), `received_on` (str), `requested_amount_inr` (int), `requested_tenor_months` (int), `purpose` (str), `declared_annual_revenue_inr` (int), `existing_annual_debt_service_inr` (int), `current_assets_inr` (int), `current_liabilities_inr` (int), `collateral_type` (str), `collateral_value_inr` (int), `export_receivables_usd` (int), `proprietor_name` (str), `city` (str), `application_language` (str) |
| `underwriting_reference` | 350 | `application_id` | What the credit policy says about each application: DSCR, ratios, grade, rate, reason codes, outcome and who must sign. Ground truth for your calculator and router. | `application_id` (str), `proposed_annual_debt_service_inr` (int), `dscr` (float), `sector_dscr_floor` (float), `meets_dscr_floor` (bool), `leverage_ratio` (float), `current_ratio` (float), `revenue_variance_pct` (float), `internal_grade` (str), `indicative_rate_pct` (float), `reason_codes` (str), `risk_band` (str), `approval_authority` (str), `auto_approve_allowed` (bool), `requires_human_signoff` (bool) |

Columns worth a note:

| Column | Meaning |
|---|---|
| `loan_applications.proprietor_name`, `city`, `application_language` | Demographic proxies. They must not change an outcome; the matched bias pairs in the eval set test exactly that |
| `loan_applications.declared_annual_revenue_inr` | What the applicant stated. `applicants.annual_revenue_inr` is the verified figure. A gap above 10% is `DOC_MISMATCH`; above 25%, a fraud hold |
| `underwriting_reference.reason_codes` | `;`-separated codes from `reason_codes` |
| `underwriting_reference.risk_band` | `approve`, `borderline` or `decline`, by the rule in the worked example above |
| `loan_applications.requested_tenor_months`, `collateral_value_inr` | Tested against `risk_grades.max_tenor_months` (and the sector's) and `collateral_cover_pct` of the amount. About one application in six asks for more than the lender offers: `TENOR_ABOVE_LIMIT`, `COLLATERAL_SHORTFALL` |
| `sector_policies.at_sector_cap` | True when current exposure has reached the cap. Any new loan in that sector is `SECTOR_CAP` and goes to a human |
| `signatories.approval_limit_inr` | Empty for the Board Credit Committee, which has no limit |

Known limits of the original tables. They are kept exactly as v1.0.0 wrote them, the validator reports each as a `NOTE`, and `--fresh-table-rng` removes them:

- `bank_statements` holds 1,200 rows drawn at random: every applicant has fewer than 18 months, 9 have none, and inflows are unrelated to revenue. `--fresh-table-rng` writes up to 18 consecutive months per applicant, sized to the business.
- 155 of 220 `past_decisions` contradict themselves (an approved amount on a decline, or a signatory without authority for the amount). Treat them as history of mixed quality.

### ShopSense (`shopsense`)

Twenty tables. The first five existed in v1.0.0 and are byte-identical; the other fifteen were added in v1.0.4.

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

How the tables join:

```
customers.customer_ref ──< orders, goodwill_credits, support_tickets     customers ──1 customer_profiles
products.sku ──< orders.sku           products.seller_id >── sellers     products.category >── category_policies
orders.order_ref ──1 shipments, order_fulfilment          orders ──< refunds, replacements, goodwill_credits, support_tickets
orders.payment_method >── refund_processing_times         shipments.carrier >── carriers
refunds.reason_code >── refund_rules                      order_fulfilment.(service_tier, delivery_zone) >── delivery_services
refunds.approved_by, replacements.approved_by, goodwill_credits.issued_by, support_tickets.handled_by >── refund_authority.approver
support_tickets.refund_id / replacement_id / credit_id >── refunds / replacements / goodwill_credits
```

Worked examples:

- **Refund for a change of mind.** Take the amount paid (`orders.order_value_inr`) and the product's category. Check the request is on or before `order_fulfilment.return_by`. If the item was opened, subtract `restocking_fee_pct` of the amount paid, rounded to the nearest rupee; subtract `return_pickup_fee_inr`. An opened Electronics item bought for 11,500 refunds 11,500 - 1,725 - 99 = 9,676. Every other reason in `refund_rules` refunds 100%.
- **Can the assistant approve it?** Not if the refund is above 2,000 (`refund_authority`: team lead to 10,000, operations manager to 50,000, finance above), not if `customer_profiles.automated_refunds_allowed` is false, and not if any row of `escalation_triggers` applies, for example a third contact about the same order in `support_tickets`.
- **Is the order late, and what is owed?** `order_fulfilment.days_late` and `delay_credit_due_inr` give the answer for a delivered order (3 to 5 days late: 100; 6 or more: 250). A shipped order still undelivered 10 days after `promised_by` is lost in transit: full refund or replacement.

| Table | Rows | Key | What it holds | Columns (type) |
|---|---|---|---|---|
| `customers` | 500 | `customer_ref` | Customer accounts: tier, lifetime orders, return rate and the abuse flag. | `customer_ref` (str), `display_name` (str), `city` (str), `tier` (str), `joined_on` (str), `lifetime_orders` (int), `return_rate` (float), `flagged_for_abuse` (bool) |
| `products` | 600 | `sku` | The catalogue: category, price, seller, stock, warranty months. | `sku` (str), `title` (str), `category` (str), `price_inr` (int), `seller_id` (str), `in_stock` (bool), `warranty_months` (int) |
| `orders` | 1,500 | `order_ref` | Orders with amount paid, payment method, status and delivery promise. | `order_ref` (str), `customer_ref` (str), `sku` (str), `quantity` (int), `order_value_inr` (int), `placed_at` (str), `payment_method` (str), `status` (str), `delivery_promise_days` (int), `actual_delivery_days` (int, nullable) |
| `shipments` | 1,500 | `tracking_id` | One shipment per order: carrier and last scan. | `tracking_id` (str), `order_ref` (str), `carrier` (str), `last_scan` (str), `last_scan_at` (str), `scan_location` (str) |
| `refunds` | 320 | `refund_id` | Past refund requests with amount, reason, status and approver. | `refund_id` (str), `order_ref` (str), `amount_inr` (int), `reason_code` (str), `status` (str), `approved_by` (str), `requested_on` (str) |
| `policy_limits` | 15 | `limit` | The policy's single-number thresholds, each with the document that states it: automated refund cap, goodwill cap, lost-in-transit days, repeat-contact threshold, return-rate threshold and more. | `limit` (str), `value` (float/int), `unit` (str), `document` (str), `description` (str) |
| `category_policies` | 8 | `category` | Per category: return window, whether an opened item can come back, restocking fee, packaging rule, pickup fee, defect claim period, warranty eligibility, handling rule. | `category` (str), `policy_document` (str), `return_window_days` (int, nullable), `opened_item_returnable` (bool), `restocking_fee_pct` (int), `original_packaging_required` (bool), `return_pickup_fee_inr` (int, nullable), `defect_claim_days` (int), `warranty_eligible` (bool), `handling_rule` (str) |
| `refund_authority` | 5 | `approver` | Who may approve a refund of what size. `auto` is the assistant acting alone. | `approver` (str), `role` (str), `max_refund_inr` (int, nullable), `is_human` (bool) |
| `refund_rules` | 7 | `reason_code` | Per refund reason: percentage refunded, whether the restocking fee applies, who pays return shipping, whether the item must come back. | `reason_code` (str), `refund_pct` (int), `restocking_fee_applies` (bool), `return_shipping_paid_by` (str), `return_required` (bool), `applies_when` (str) |
| `refund_processing_times` | 5 | `payment_method` | Where a refund goes and how long it takes, per payment method. | `payment_method` (str), `refund_destination` (str), `promise` (str), `max_business_days` (int) |
| `delivery_services` | 6 | `service_tier + delivery_zone` | Promised delivery days for express, standard and economy, to metro and non-metro addresses. | `service_tier` (str), `delivery_zone` (str), `promise_days` (int) |
| `delay_compensation` | 3 | `min_days_late` | The delay ladder: goodwill credit owed by days late. | `min_days_late` (int), `max_days_late` (int, nullable), `goodwill_credit_inr` (int) |
| `escalation_triggers` | 8 | `trigger` | The eight conditions that send a ticket to a human, and where it goes. | `trigger` (str), `description` (str), `routes_to` (str) |
| `carriers` | 5 | `carrier` | The five carriers: days to answer a claim, tracking URL pattern, claims contact. | `carrier` (str), `claim_response_business_days` (int), `tracking_url` (str), `claims_contact` (str) |
| `sellers` | 120 | `seller_id` | Marketplace sellers: fulfilment model, rating, status, and who handles their warranty claims. | `seller_id` (str), `seller_name` (str), `city` (str), `fulfilment` (str), `seller_rating` (float), `onboarded_on` (str), `status` (str), `warranty_handled_by` (str) |
| `order_fulfilment` | 1,500 | `order_ref` | One row per order with dates instead of day counts: service tier, zone, promised and delivered dates, days late, delay credit due, last day to return, warranty end. | `order_ref` (str), `service_tier` (str), `delivery_zone` (str), `promised_by` (str), `delivered_on` (str, nullable), `days_late` (int, nullable), `delay_credit_due_inr` (int, nullable), `return_by` (str, nullable), `warranty_until` (str, nullable) |
| `goodwill_credits` | 155 | `credit_id` | Goodwill credits issued. Never above the cap, one per order, never on a refunded order. | `credit_id` (str), `order_ref` (str), `customer_ref` (str), `amount_inr` (int), `reason` (str), `issued_by` (str), `issued_on` (str) |
| `replacements` | 63 | `replacement_id` | Replacement requests with reason, status and approver. The replace half of the refund/replace API. | `replacement_id` (str), `order_ref` (str), `reason` (str), `requested_on` (str), `status` (str), `approved_by` (str, nullable), `rejection_reason` (str, nullable) |
| `customer_profiles` | 500 | `customer_ref` | Preferences (language, channel, refund destination, contact window) and where the fraud standard leaves the account. | `customer_ref` (str), `preferred_language` (str), `preferred_channel` (str), `refund_preference` (str), `contact_window` (str), `orders_on_record` (int), `refunds_last_90_days` (int), `over_return_rate_threshold` (bool), `serial_refund_requester` (bool), `review_status` (str), `automated_refunds_allowed` (bool) |
| `support_tickets` | 861 | `ticket_id` | Past tickets per customer and order: intent, sentiment, contact number, resolution, who handled it, and the refund, replacement or credit it led to. | `ticket_id` (str), `customer_ref` (str), `order_ref` (str, nullable), `opened_at` (str), `channel` (str), `intent` (str), `sentiment` (str), `contact_number` (int), `resolution` (str), `handled_by` (str), `refund_id` (str, nullable), `replacement_id` (str, nullable), `credit_id` (str, nullable), `csat` (int, nullable) |

Columns worth a note:

| Column | Meaning |
|---|---|
| `category_policies.return_window_days` | Days from delivery. Empty for Groceries, which is non-returnable |
| `category_policies.warranty_eligible` | False for Apparel, Beauty and Groceries: a warranty period on such a listing gives no cover |
| `order_fulfilment.delivered_on` | Empty until delivered. Where `orders.actual_delivery_days` is blank on a delivered order, it is taken as delivered on the promised date |
| `order_fulfilment.delay_credit_due_inr` | What the delay ladder allows on a late order the customer kept; 0 on a returned one. `goodwill_credits` shows whether it was issued |
| `support_tickets.refund_id`, `replacement_id`, `credit_id` | The outcome the ticket led to. A ticket is linked only to a refund the policy allows, so in default mode most rows of `refunds` have no ticket |
| `order_fulfilment.return_by`, `warranty_until` | Last day for a change-of-mind return, and last day of warranty cover. Empty where none applies |
| `customer_profiles.review_status` | `none`, `cleared`, `under_review` or `flagged`. Internal: the assistant must never reveal it. `automated_refunds_allowed` is false for the last two |
| `support_tickets.contact_number` | 1 for the first contact about an order, 2 for the second, and so on. The third goes to a human |
| `support_tickets.handled_by` | `auto` (the assistant alone), `agent`, `team_lead`, `ops_manager` or `finance` |
| `refunds.approved_by` | Same values. In default mode it is set even on refunds still `requested` |

Known limits of the original tables. They are kept exactly as v1.0.0 wrote them, the validator reports each as a `NOTE`, and `--fresh-table-rng` removes them:

- `orders.order_value_inr` is not price x quantity on 1,352 of 1,500 orders. Treat it as the amount paid: every refund is calculated on it.
- `shipments.last_scan` disagrees with `orders.status` on 1,199 orders, and 173 shipped orders are months past their promised date. Use `orders.status` and `order_fulfilment`.
- Of 320 `refunds`, 126 exceed the order value, 78 were approved below the required tier and 133 are dated before the order. Use `refund_authority` and `refund_rules` for what should happen.
- 129 products in Apparel, Beauty and Groceries show a warranty period. `category_policies.warranty_eligible` and `order_fulfilment.warranty_until` are correct.

`--fresh-table-rng` changes the *values* in the original tables of the four
domains above so they agree with each other and with the new tables (see
`CHANGELOG.md` v1.0.2 and v1.0.4). It never changes the columns. Use it for a
new project; keep the default if your team already built on the tables.

## Three design decisions worth knowing

**Corpus is emitted as both markdown and PDF, deliberately.** The PDF
renderer is lossy — it flattens heading structure the way real policy PDFs do.
If your M4 chunker only performs well on the markdown copy, it is not ready
for the PDF, and the PDF is what production looks like.

**Every intake record carries a `ground_truth` block.** That is your M1
parsing accuracy metric for free, and your M5 routing labels. Do not throw it
away when you load the records.

**The eval set mixes model-written and hand-written cases.** A model asked to
attack a corpus it just wrote produces polite attacks. The `-EV-9xx` cases in
each domain are hand-written to actually break things: prompt injection,
authority-limit probes, false premises, and impossible sensor readings. The
WealthPilot set includes *matched bias pairs* — identical financials, one
varying demographic proxy — where any divergence in outcome is a fair-lending
failure rather than a judgement call. Hand-written cases that ask for a figure
compute their expected answer from the same constants the documents and
tables are built from.

**One set of facts feeds the documents, the tables and the eval answers.**
Each domain module starts with its policy as constants: return windows,
co-pays, playbook positions, DSCR floors, criticality bands. The document
prompts quote them, the mock API tables store them, and the hand-written eval
answers are computed from them. Model-written eval cases are given the corpus
text, and a factual or multi-hop case whose figures are not in the documents
it cites is discarded. Before v1.0.4 most of these figures were left to the
model, so a document, a table and an eval answer could each say something
different.

## When things go wrong

Free tiers fail in predictable ways, and the toolkit is built to survive them:

- **Rate limited** → exponential backoff with jitter, then a clear error.
  Switch with `--provider ollama` or `--provider openrouter`.
- **A document is refused** by a safety filter → that document is skipped and
  named; the run continues. Common for clinical and hazardous-procedure
  content. Generate the rest, then write the refused one by hand or use a
  local model.
- **The run dies partway** → re-run the same command. Completed corpus
  documents are skipped, so you only pay for what is missing. A
  `manifest.json` marked `"complete": false` is written even on failure.
- **Fewer intake records than requested** → the generator stops rather than
  looping, and warns. Re-run to top up.
- **`No module named 'pydantic_core'`** or another import error → the virtual
  environment is half installed. The toolkit now prints the fix instead of a
  traceback: `python -m pip install --force-reinstall --no-cache-dir -r
  requirements.txt`, and if that fails, rebuild the environment with
  `python -m venv --clear .venv`.

## Validating generated data

```bash
python -m tests.validate_data --domain plantguard     # one domain
python -m tests.validate_data --domain all            # all five, with a summary
```

Reads `data/<domain>/` and compares it with what this version generates. No
API key, no network, nothing written. Exit status 1 if any check fails.

| Section | Checks |
|---|---|
| manifest | Present and readable; last run finished; generated by this toolkit version; `contains_real_personal_data` is false |
| corpus | Every planned document exists as `.md` and `.pdf`; the PDF is readable; no document is empty, unusually short, or a copy of another; `index.json` lists them all |
| intake | File present; every line is a JSON object; record count; unique `record_id`; `ground_truth` present; each declared field present in at least 80% of records |
| tables | Every table present as CSV and JSON; columns, order and value types match the schema; row counts; CSV agrees with JSON; every ID that refers to another table resolves; values identical to a fresh build for the manifest's seed |
| eval | Case count; all seven fields; unique IDs; every hand-written `-EV-9xx` case present and current; required categories covered; every `must_cite` title is a real corpus document; the figures in factual and multi-hop answers appear in the documents they cite |
| plantguard | Criticality follows from its three factors; technicians resolve; intake events name real assets; manuals cite real inventory parts; the planning document states the criticality matrix |
| careflow | The cost-share schedule covers every plan; the pre-authorisation matrix names the procedures in `procedures`; every referral agrees with the rule for its procedure and plan; intake messages name registered patients |
| lexops | Every risk score equals the sum of the contract's clause points; the risk-scoring document names the clause families; each playbook section names its deviation; intake requests name real counterparties |
| wealthpilot | Every DSCR equals EBITDA over existing plus proposed debt service; the risk grading document covers every grade; the adverse action standard names the reason codes; intake applications match `loan_applications` and their labels match the reference |
| shopsense | Every order agrees with the delivery promise and the delay ladder; goodwill credits respect the cap and the no-stacking rule; replacements and ticketed refunds were decided at the right tier; no past ticket was handled automatically despite an escalation trigger; category addenda state the return window and restocking fee; the refund matrix states every threshold; intake tickets name real orders and customers |

`NOTE` marks a known limit of the original tables in default mode, with the
table to use instead. It is not a fault and never changes the verdict.
`WARN` means usable but not what a fresh run produces, most often data from an
older version. `FAIL` means missing or malformed. Each one prints the command
that fixes it.

Options: `--only <stages>` to check some stages, `--intake N`, `--eval-items N`
and `--corpus-docs N` if you generated a smaller set on purpose, `--data
<folder>` for a non-default output folder, and `--strict` to fail on warnings.

Expected fields come from each domain's `intake_fields` and
`intake_truth_fields`; expected tables, columns and types are read from the
generator itself, so the validator cannot drift from the code.

## Testing your own changes

```bash
python -m tests.test_regressions     # offline, no API key, under a minute
```

This tests the toolkit's code, not your data; for your data use
`tests.validate_data` above. If you modify a domain module, run this first. It checks referential
integrity, determinism, and that declared table names match what is built —
the failures that are otherwise invisible until M6.

## Reproducibility

Same seed ⇒ byte-identical output, including all dates (generation is anchored
to a frozen reference clock, not the wall clock). This is what lets teams be
graded against a common rubric. LLM-generated stages vary with provider
sampling; the tables and eval scaffolding do not.

```bash
python generate.py --domain shopsense --only tables --seed 42
```

## This is the starting point, not the finish line

The generator produces the *policy layer* — the documents nobody publishes in
machine-readable form. For volume and realism, layer real public data on top.
Each domain's `manifest.json` lists the datasets it was grounded against, with
licences. The headline ones:

- **LexOps** → CUAD (510 real contracts, 41 clause types, 13k expert
  annotations, CC BY 4.0). Use it as your primary contract corpus; the
  annotations double as free retrieval ground truth.
- **PlantGuard** → AI4I 2020 (CC BY 4.0) and NASA C-MAPSS. Never generate
  sensor time series with an LLM — the output looks plausible and is
  statistically wrong.
- **ShopSense** → Bitext retail/e-commerce intents (CDLA-Sharing 1.0) and
  Olist's nine-table order database.
- **CareFlow** → Synthea, which produces synthetic FHIR patient records that
  are free of privacy restrictions by construction.
- **WealthPilot** → SBA 7(a) public loan data; RBI's MSME Master Direction for
  the India context.

See the *Capstone Data Sourcing Guide* for the full treatment of each.

## Ground rules

No real personal data goes into any capstone, ever — not patient records, not
applicant files, not customer PII. Generated content is synthetic by
construction and every run writes a `manifest.json` asserting so. When you
layer in a public dataset, check its licence: several listed above are
non-commercial or share-alike, which is fine for coursework and not fine for
whatever you build next.
