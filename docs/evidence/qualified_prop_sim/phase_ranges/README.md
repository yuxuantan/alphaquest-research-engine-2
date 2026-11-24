# Separate phase size ranges, optional risk cap and Evaluation Pareto chart

This is an additive **synthetic normal-product demonstration**. Earlier shared-
range evidence remains unchanged in the parent folder. No provider parity,
real-market performance, portfolio optimum or future outcome is asserted.

The saved journey uses the same labeled synthetic NQ source through mechanics,
IS Broad, IS Narrow, OOS and the current full-period Monte Carlo assessment.
From the native IS backtest report, **Configure prop analysis** opens the real
Prop Sim form. Source checking, both numerical phases, background jobs, durable
reports and exports use the existing campaign/AnalysisStore owners.

## Inspect and reproduce

- `prop-sim.json` records distinct **58–60 MNQ Evaluation** and **38–40 MNQ Funded**
  ranges, 32 paths per size/phase, seed 42, five-weekday blocks, fees 49/129 USD,
  replacement MNQ commission 0.51 USD per side, start 2026-11-16, 90 calendar
  Funded days, two-calendar-day receipt delay and a **null/off breach cap**.
- `evaluation-report.json` / `funded-report.json`, CSVs and evidence ZIPs are
  actual native phase outputs. Inspect each candidate's configuration and
  simulation cap: Evaluation 60, Funded 40. Funded account scaling tiers still
  restrict actual exposure at the start of an account.
- `evaluation-portal.png` / `funded-portal.png` show the actual result sections.
  `evaluation-pareto.svg` is downloaded from the Evaluation chart in the portal.
- `SYNTHETIC-source.csv` and `journey.json` preserve the normal source download
  and the selected configuration/expected arithmetic information.

From the repository root:

```sh
ALPHAQUEST_PROP_SIM_EVIDENCE_DIR=/private/tmp/prop-phase-ranges-reproduction \
  .venv/bin/python -m pytest -q \
  'tests/test_prop_sim_browser.py::test_prop_sim_qualified_single_configuration_real_results_and_downloads[phase-limits]'
```

Expect exactly three rows per phase, with **58, 59, 60** versus **38, 39, 40**.
The form enforces the distinct maximums and starts with a blank optional breach
cap. The test checks/launches through the real portal, navigates away, reopens,
inspects the chart by keyboard, downloads SVG/CSV/JSON/ZIP and returns through
Job history/reload. Its temporary server stops at teardown. Use the `shared-range`
case instead of `phase-limits` to reproduce the earlier 1–3 sizing arithmetic
with the current form, writing outputs to a separate temporary directory.

Additional focused validation:

```sh
.venv/bin/python -m pytest -q tests/test_prop_sim.py \
  tests/test_prop_sim_browser.py::test_evaluation_pareto_chart_tradeoffs_ties_and_unresolved_rows \
  tests/test_workflow_navigation_browser.py::test_prop_sim_empty_qualification_boundary_and_mobile
```

## Independent expected arithmetic and observations

Each Evaluation size has **24/32 passed attempts**, so expected attempts are
`32/24 = 1.3333333` and expected acquisition cost is
`49 * 32/24 + 129 = 194.3333333 USD`. The 32 complete acquisition chains total
**616 calendar days**, giving **19.25 days** mean and **44 days** P90. All three
sizes tie on both objectives and remain frontier members. They occupy **one
shared chart point**, explicitly listing 58, 59 and 60 MNQ. No second point or
tradeoff curve is invented.

For each Funded size, all 32 paths sum to **58,500 USD received**, **2,000 USD
pending** and **60,500 USD deducted**. Dividing by 32 gives **1,828.125**, **62.5**
and **1,890.625 USD**. Median/P10 receipts are zero, first-payout probability is
16/32, inactivity is 24/32 and drawdown breach is zero. All sizes tie; the rank-1
identifier is a deterministic tie break, with two alternatives shown. No cap
is applied despite breach remaining visible as a measurement.

The API test also uses an independent small arithmetic oracle against the
actual Evaluation kernel: daily net 50 USD per NQ-equivalent exposure means
60 MNQ earns `50 * 60 / 10 = 300 USD` per session, so the 3,000 USD target takes
exactly **10 sessions** across eight deterministic paths. A hidden 40-MNQ cap
would instead take **15 sessions**. This verifies the cap passed by the new
request, alongside phase-specific candidate membership and cache identities.

The separate chart presentation test retains its oracle only in tests. Points
(10 days, 100 USD) and (5 days, 200 USD) are connected frontier tradeoffs;
(12 days, 300 USD) is grey/dominated; a duplicate (10,100) lists both tied sizes;
a null/unresolved candidate is excluded from geometry but retained in the table.
It checks the axis orientation, two-point frontier line, keyboard row highlights
and explicit empty plot when every candidate is unresolved. These display-only
oracle values are not included in this product evidence or its catalogue.

## Rejections, compatibility and actual-user reproduction

The API rejects Evaluation 61 MNQ, Funded 41 MNQ, inverted ranges, multiple
selected configurations and forged qualification. Changing one phase's range
leaves the other phase's calculation key unchanged. A blank/null breach cap
removes only that risk constraint; explicit caps still apply. Old shared-range
requests and saved declarations remain readable/idempotent, and earlier reports
keep their original explicit caps and numerical configuration.

For the actual library, open `http://127.0.0.1:8000/#prop-sim`, choose a qualified
configuration and enter distinct ranges. Leave **Optional Funded breach cap**
blank to rank expected cash without that constraint. Check, run and inspect the
Evaluation chart and both tables. To try every supported size, use Evaluation
1–60, Funded 1–40 and 500 paths per size so the existing report-resource bound
is respected. These remain conditional fixed-signal-path research estimates.

The chart also appears immediately when reopening an existing completed run;
it uses saved results without recalculation. Old saved runs show their original
25% cap in the form; starting a new uncapped run requires the new blank setting.
The five years of historical IS data supply sampled scenarios; they are not a
requirement for a single Funded account to survive five future years. Its modeled
horizon is separately configured and accounts can terminate through inactivity
or completion of payouts as well as drawdown failure.
