# Prop Sim conclusions and next steps — 14 November 2026

This presentation increment uses the existing **Prop Sim** page, saved report
summaries and paper-review controls. It changes no numerical owner, policy,
qualification verdict, frozen family, sampling or path count. The JavaScript
view reads the server's saved statuses and does not decide eligibility again.

## Normal user journey

1. Open a campaign-qualified IS backtest, then **Configure prop analysis**.
2. Configure the account and independent phase size searches; click **Run IS
   and OOS** once. The existing worker continues after navigation.
3. Reopen the saved simulation. **Conclusion & next steps** summarizes Evaluation
   and Funded separately, before the IS findings and detailed result tables.
4. Read the phase conclusion and **Why this is the next step**. It distinguishes
   evidence minima, inconclusive/failed confidence comparisons, inner account-MC
   precision and forward execution issues. Ratios use the saved check's limit
   and interval, displayed to two decimal places.
5. **Inspect saved evidence** opens the appropriate existing report/history card.
   **Review diagnostic options** opens the existing controls without launching a
   job. Diagnostic extra paths do not automatically change a saved OOS verdict.
   **Review replacement cash flow** opens the existing portfolio configuration
   mode; its supported-source requirements still apply.
6. A current historical GO offers **Open paper execution review**, including for
   automatic simulations. This opens the existing supplied-paper workflow. It
   does not create observations, launch a job or authorize trading by itself.

| Saved evidence | Portal conclusion / next action |
| --- | --- |
| Running / absent qualification | Hold deployment; wait for or complete qualification. Job completion alone is not a passing verdict. |
| INSUFFICIENT_EVIDENCE | Hold deployment; keep the campaign in research and inspect the specific evidence/precision/confidence blockers. |
| NO_GO | Do not deploy those sizes under the saved policy; investigate failed checks and economics. Keep the original freeze/report. |
| Historical GO, forward pending | Paper execution review next, for those GO sizes only. |
| Historical GO, forward NO_GO | Hold deployment; resolve recorded execution issues. |
| Historical and forward GO | Review replacement cash flow, loss budget and provider/broker controls before considering a limited pilot. No automatic live approval. |
| Mixed family | List GO, inconclusive, NO-GO and unassessed counts; each row has its own next step. No OOS replacement selection. |
| Earlier numerical/policy version | Show its original outcome as historical; do not promote it to current qualification. |

Campaign checks are described as passed **at assessment time** only when every
displayed row records passing prerequisites. An inconclusive/failed prop sizing
assessment does not revoke those stored campaign results. Earlier policy versions
and unknown verdicts never silently become a new current pass.

## Actual saved simulation

Open the user's existing simulation:

```text
http://127.0.0.1:8000/#prop-sim?analysis=ede834c9fea44f2fa663e481dd8d4582
```

Expected observations for the preserved reports:

- Evaluation: three inconclusive sizes, zero GO and zero NO-GO.
- Funded: two inconclusive sizes, zero GO and zero NO-GO.
- Both show the original campaign checks as passed at assessment time, and the
  actual confidence-interval and account-MC precision blockers.
- Example Funded 13 MNQ: mean-receipt OOS/IS 0.80, historical interval
  [0.13, 3.64], required lower bound at least 0.70. It is inconclusive, not a
  demonstrated failure. The saved inner-precision check is also unmet.
- These original reports predate the earlier Funded preparation numerical-owner
  change. The portal therefore labels them **historical assessment only** and
  does not claim current qualification. That version incompatibility predates
  this UI increment; viewing the new explanation does not require a rerun.

The GET-only browser verification inspected both saved report summaries, opened
the existing history/evidence table and checked desktop and 390px mobile layouts.
It submitted zero POST requests, created no new analysis and preserved the exact
report/ZIP hashes, frozen packages and assessment history. The existing user's
port-8000 server remained running without restart.

Saved evidence:

- [Overview](overview.png), [mobile overview](mobile-overview.png).
- [Evaluation explanation](evaluation-conclusion.png),
  [Funded explanation](funded-conclusion.png),
  [mobile explanation](mobile-conclusion.png).
- [Saved qualification summaries](saved-qualification-summaries.json): actual
  original source/metric/verdict records, without the large bootstrap arrays.
- [Live verification](live-verification.json): original/after report and ZIP
  hashes, no-POST/no-new-job checks and rendered conclusions.

The original sealed report downloads remain in the ordinary product history:
Evaluation `a11f6078cef3415c96ac0c8f1d423921` and Funded
`609ec63f9b2f4af2ad84c40d920eb484`. No replacement report store is introduced.

## Synthetic automatic product journey

The [synthetic automatic evidence](synthetic-automatic/journey.json) follows an
ordinary saved backtest → Prop Sim configuration → one initial Run → navigation
away → sealed IS/OOS reports → reopening → paper-review action → mobile result
journey. Its source is explicitly **SYNTHETIC frozen OOS**, not a real performance
claim. See the [configuration](synthetic-automatic/configuration.png),
[Evaluation result](synthetic-automatic/evaluation-complete.png),
[Funded result](synthetic-automatic/funded-complete.png),
[mobile result](synthetic-automatic/mobile.png),
[saved simulation](synthetic-automatic/simulation.json) and the
[Evaluation](synthetic-automatic/evaluation-summary.json) /
[Funded](synthetic-automatic/funded-summary.json) saved presentation summaries.

Independent constant-day expectations are unchanged: Apex acquisition cost
USD 49 + 129 = **178**, mean time **2 calendar days**, and Funded receipts
**USD 13,000** across its six full payout rungs. Both IS sizes 9–10 tie, so the
existing automatic policy freezes 9 MNQ. Every historical ratio and interval
bound is 1.00; the eight account paths and 10,000 historical refits are retained.
Historical GO therefore leads to paper review; forward execution remains PENDING.
The paper-review action opens the existing supplied-observation controls without
submitting pretend paper data. No live readiness is inferred from this fixture.

The generated full report ZIPs and isolated library for this exact new run are
retained locally in `/private/tmp/aq-prop-conclusion-final-evidence/apex-50k-eod/`
and `/private/tmp/aq-prop-conclusion-final-tests/`. Existing durable independent
arithmetic qualification exports remain under
[funded-preparation](../funded-preparation/README.md); this increment does not
duplicate their numerical engines or require replacing those immutable reports.

## Boundary checks and reproduction

[Display-only boundary evidence](display-boundaries/conclusion-boundaries.json)
records controlled HTTP presentation fixtures for inconclusive intervals,
precision-only blockers, insufficient source evidence, NO-GO, mixed families,
forward failures/passes, historical results, running jobs and unassessed reports.
These are test fixtures over a normal sealed product run. They do not rewrite
saved numerical reports or manufacture source/campaign results.

Screenshots: [inconclusive](display-boundaries/inconclusive.png),
[failed](display-boundaries/failed.png), [mixed](display-boundaries/mixed.png),
[historical](display-boundaries/historical.png),
[mobile](display-boundaries/mobile.png). The fixture checks zero POSTs from
rendering, unchanged report seals and unchanged assessment counts.

Run only the affected journeys, using installed Chrome if the bundled Playwright
browser is absent:

```sh
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome \
ALPHAQUEST_QUALIFICATION_SEED_LIBRARY="$PWD/artifacts/funded-preparation-20261114/libraries/apex-50k-eod" \
.venv/bin/python -m pytest -q \
  'tests/test_prop_sim_automatic_browser.py::test_one_run_finishes_all_four_simulations_after_navigation[apex-50k-eod]' \
  tests/test_prop_sim_automatic_browser.py::test_saved_conclusions_distinguish_inconclusive_failure_forward_and_history \
  tests/test_prop_sim_assessment_reuse_browser.py::test_current_result_reopens_without_jobs_and_history_loads_on_demand
```

The optional seed is copied into each temporary test library; it is not mutated.
Omit that variable to regenerate the qualified synthetic campaign, which takes
longer and is unnecessary for this presentation change. The automatic browser
journey also passed with a freshly qualified source during this increment.
Temporary test servers and owned browser/worker processes are stopped on cleanup;
no persistent demonstration server was added.
