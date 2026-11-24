# Qualified campaign → Prop Sim: saved normal-product evidence

This is **synthetic** NQ research data, not market performance, a provider parity
claim or a future return forecast. Files were generated through normal datasets,
campaign mechanics/Broad/Narrow/OOS/Monte Carlo, native phase source checks,
CampaignStore, AnalysisStore and the actual Prop Sim portal. No alternate API,
calculation engine or result store was created for this demonstration.

Current extension: [separate phase ranges, optional default-off breach cap and
Pareto chart](phase_ranges/README.md) supersede the shared form below. The files
in this folder preserve the original `53a973f` product snapshot and its explicit
25% cap. The current browser test has `shared-range` and `phase-limits` cases;
select `[shared-range]` to repeat the low-size arithmetic journey, or follow the
new guide for the 60/40 boundaries. Write reproduction output to a temporary
folder to preserve these snapshots.

## Inspect the delivered outputs

- `SYNTHETIC-source.csv`: the labeled synthetic source from the normal dataset API.
- `prop-sim.json`: saved parent configuration, qualification and phase references.
- `journey.json`: source/workflow IDs, settings and saved metric summary.
- `evaluation-report.json`, `funded-report.json`: normal sealed phase reports,
  including source identities, complete candidates, settings, paths and model hashes.
- `evaluation-results.csv`, `funded-results.csv`: actual product table exports.
- `evaluation-analysis.zip`, `funded-analysis.zip`: normal downloadable evidence
  bundles including source checks, settings and calculations.
- `evaluation-portal.png`, `funded-portal.png`: the actual portal result sections.

These report IDs belonged to an isolated test catalogue, stopped at test teardown.
They are inspectable files, not links into the user's live catalogue. Earlier
Monte Carlo and phase evidence directories remain unchanged.

## Reproduce the saved demonstration

From the repository root, with the existing `.venv` and Chromium browser extra:

```sh
ALPHAQUEST_PROP_SIM_EVIDENCE_DIR=/private/tmp/qualified-prop-sim-reproduction \
  .venv/bin/python -m pytest -q 'tests/test_prop_sim_browser.py::test_prop_sim_qualified_single_configuration_real_results_and_downloads[shared-range]' \
  tests/test_workflow_navigation_browser.py::test_prop_sim_empty_qualification_boundary_and_mobile
```

The test creates a temporary independent library/server and shuts the server down
at teardown. It creates the synthetic native source through the normal API,
executes/qualifies the real campaign stages and current 5,000-path Monte Carlo
assessment, then opens the real IS source backtest report. **Configure prop
analysis** opens Prop Sim with that eligible configuration preselected. It checks
source/settings, runs both phase searches, navigates away, reopens saved results,
downloads reports/CSV/ZIPs, follows Job history back to Prop Sim, and reloads.
No background job is interrupted by navigation. The empty-library/mobile check
shows no fictional sources, no enabled Run action, and the four main nav links.

The saved scenario is 1–3 MNQ, 32 paths per size per phase, seed 42, five-weekday
blocks, 49 USD purchase / 129 USD activation, replacement MNQ commission 0.51 USD
per side, start 2026-11-16, no declared closures, 90 calendar Funded days,
two-calendar-day receipt delay and a 25% maximum breach-probability constraint.
The source helper removes weekend trades and scales the arithmetic prices into
NQ exposure; its explicit synthetic fixture is in `tests/test_prop_sim.py`.

## Independent arithmetic and boundary observations

Evaluation expected attempts are `1 / p`, and acquisition cost is `49 / p + 129`.
The saved empirical attempt counts give:

| MNQ | Passed / attempted | Expected cost USD | Mean calendar days | Pareto |
| --- | --- | --- | --- | --- |
| 1 | 21 / 32 | 203.6666667 | 35.6875 | No |
| 2 | 24 / 32 | 194.3333333 | 19.25 | Yes |
| 3 | 24 / 32 | 194.3333333 | 19.25 | Yes |

Sizes 2 and 3 tie on both objectives, so both remain. There is no hidden selected
Evaluation size. The calendar-chain durations sum to 1,142 days for size 1 and
616 days for each of sizes 2/3; divide each by all 32 chains. P90 durations are
77 and 44/44 calendar days respectively.

For **each** Funded size, direct addition of all 32 paths gives 58,500 USD cash
received, 2,000 USD pending cash and 60,500 USD account deductions. Their means
are 1,828.125, 62.5 and 1,890.625 USD respectively. Received plus pending equals
deductions here because the modeled trader share is 100%. Pending cash is not
credited into received cash. Median/P10 receipts are zero; only 16/32 accounts
reach a first payout, 24/32 become inactive, and none breach. All starts count
in the means; an average of payout recipients alone would be wrong. The three
sizes tie in expected cash, so the deterministic rank-1 size does not establish
a uniquely better size. The portal displays tied/near-tied alternatives.

To recompute directly from the saved downloads:

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
root = Path('docs/evidence/qualified_prop_sim')
for phase in ('evaluation', 'funded'):
    report = json.loads((root / (phase + '-report.json')).read_text())
    for row in sorted(report['calculations']['candidates'],
                      key=lambda r: r['manifest']['configuration']['micros']):
        m = row['metrics']
        if phase == 'evaluation':
            expected = 49 / m['pass_probability'] + 129
            assert abs(expected - m['cost_per_funded']) < 1e-8
            expected = sum(p['observed_calendar_days'] for p in row['paths']) / 32
            assert expected == m['expected_calendar_days_to_funded']
        else:
            expected = sum(p['cash_received'] for p in row['paths']) / 32
            assert expected == m['expected_funded_cash_payouts_within_horizon']
            assert sum(p['pending_cash'] for p in row['paths']) == 2000
        print(phase, row['manifest']['configuration']['micros'], expected)
PY
```

Additional focused checks:

```sh
.venv/bin/python -m pytest -q tests/test_prop_sim.py tests/test_job_history.py
```

These reject multiple selections (422), forged/currently incompatible Monte
Carlo references (409), and tampered Monte Carlo report evidence, even on a cached
launch. Saved historical Prop Sim results remain readable. Changing Evaluation
fees leaves the Funded calculation identity unchanged; changing the Funded
horizon leaves Evaluation unchanged. Source-risk admission, idempotence, frozen
Narrow preservation, job links, exports and catalogue reopening are checked.
No full 180-check research suite is required for this orchestration increment.

## Reproduce with an existing qualified real campaign

1. Open `http://127.0.0.1:8000/#prop-sim` and choose the qualified configuration.
   Only current full-chain passes are listed. Select one configuration.
2. Inspect its frozen parameters and source/campaign links. Defaults are 1–10 MNQ
   and 1,000 paths per size/phase. Set the declared calendar/start date, fees,
   replacement commission, horizon and breach constraint before running.
3. Click **Check source and settings**. Expect compatible native phase source
   checks and the declared size count for each phase; an unsupported source
   shows a rejection and does not enable Run.
4. Click **Run Evaluation and Funded**. The saved URL is
   `#prop-sim?analysis=<id>`. Navigate away/reopen while jobs continue; use Job
   history or **Stop running analyses** if necessary.
5. Expect a resolved Evaluation cost/time frontier with unresolved/censored sizes
   retained, plus the separate Funded all-start cash ranking. Inspect failures,
   uncertainty, inactivity and receipt details, then download CSV/JSON/ZIP.
6. Reload or choose this run under **Saved prop simulations**. Expect the same
   sealed results, not new draws. Changed settings require another source check
   and a new saved run; the prior report remains available.

A normal real run is already saved in the user's local library as
`58d1433331a2429e9a6f0032a6ca108b` (not included as synthetic fixture output).
At the displayed defaults its resolved Evaluation frontier contains 10 MNQ,
with pass probability 0.131, expected acquisition cost 503.0458015 USD and mean
184.205 calendar days. Under the 25% Funded breach constraint, 4 MNQ ranks first:
mean 90-day receipts 54 USD, breach 0.172 and first-payout probability 0.035.
These are conditional local-model estimates, not trading advice or a prediction.

The portal exposes provider-rule provenance: current local 21-session
expiry/inactivity and exactly-50% consistency differ from reviewed provider
calendar/boundary rules. IS sizing after OOS-based admission is post-screening
research. Conservative held-OHLC bounds are not measured tick excursions, fixed
signals do not rerun under account pauses, calendars/fees/receipt delay are
assumptions, and no multi-source portfolio allocation has been implemented.
