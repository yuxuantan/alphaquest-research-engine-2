# Prop Sim OOS policy and chronological account starts — 13 November 2026

This is saved evidence from the **actual qualified Prop Sim product workflow**.
All prices/dates are labeled **SYNTHETIC** test data, including dates later than
the run date. These outputs are not market performance, future outcomes, Bridge
parity or provider certification. No external executable/result table supplies
production calculations.

## Use an existing compatible simulation

1. Refresh its usual `#prop-sim?analysis=...` page. Existing IS reports and frozen
   choices remain. Choose/freeze up to four eligible sizes per phase if needed.
2. Under **Declare OOS assessment limits**, enter Evaluation maximum mean
   acquisition cost and maximum mean calendar days, or Funded minimum mean cash
   receipts over its frozen horizon. Declare evidence minima and start count;
   **Save assessment limits** permanently saves them for this simulation. There
   are no prefilled business limits. Prior Prop Sim OOS attempts make this a
   retrospective declaration; strategy qualification already accessed OOS too.
3. Click **Run OOS assessment**. A completed compatible sealed OOS report is
   reused without new MC calculation; otherwise the normal local phase worker
   performs OOS. Each frozen size shows PASS, FAIL or INCONCLUSIVE, plus separate
   deterioration warnings. Expand its review for limits, evidence, cash/time
   distributions, request-versus-receipt milestones and MC uncertainty.
4. Click **Check account-start sensitivity** after OOS completes. It runs only
   the predefined chronological accounts, with equal full windows. Inspect every
   start and the zero/censor-inclusive ranges. Date selection uses coverage, not
   returns. Overlapping starts are dependent scenarios, not independent trials.
5. Reopen after navigating away/reloading. Use Job history/progress and the
   existing assessment report/evidence ZIP links. In each ZIP, inspect
   `assessment_policy.json`, `economic_assessment.json` and, for account starts,
   `account_start_sensitivity.json`. Original IS/OOS reports are retained.

Business thresholds must reflect the user's economics. The synthetic example's
$500/180-day Evaluation limits and $100 Funded minimum are demonstration values,
not recommendations. The count defaults to five (2–12 supported). Funded uses
its frozen 90-day horizon here; Evaluation's 180-day diagnostic window is its
declared maximum acceptable mean, not a new provider deadline or MC horizon.
If coverage cannot supply enough full windows, sensitivity is INCONCLUSIVE.
No replacement accounts or portfolio allocation are added.

## Reproduce the complete isolated product demonstration

From the repository root:

```sh
ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR=/private/tmp/aq-oos-policy-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey

.venv/bin/python -m pytest -q \
  tests/test_prop_assessment_review.py \
  tests/test_prop_evaluation_validation.py \
  tests/test_campaign_assessments.py

.venv/bin/python docs/evidence/qualified_prop_sim/oos-policy-starts/verify_outputs.py
```

The browser journey uploads synthetic prices via the normal dataset API, runs
mechanics/Broad/Narrow/OOS/full-period-MC qualification, opens the normal Prop Sim
page with its saved IS source, checks and runs independent searches, freezes
12 MNQ, declares limits, executes OOS/account-start/optional diagnostic jobs,
downloads normal reports and verifies reload and a 390-pixel mobile viewport.
The temporary server shuts down at fixture teardown; no persistent server is
started or existing user job stopped. Synthetic catalogues are isolated.

## Independently expected observations

Both selected phase sizes are **12 MNQ**, Lucid's explicitly purchased 50%
consistency add-on, fixed DLL on, $99.50 purchase price, zero activation fee,
$0.50 commission per MNQ side, seed 42/block 5 and 16 paths. All 16 paths enter means.
The report stores a separate review source hash; all 33 existing numerical source
fingerprints for each phase remain unchanged from the prior commit.

Evaluation OOS mean acquisition cost is **$130.59375** and mean calendar time
**23.25 days**. These are the sums of every path's paid fees and funding time,
divided by 16. They pass $500/180 days but generate adverse-change warnings against
IS $99.50/13.875 days. First-account pass drops from 100% to 81.25%, a change of
**−18.75 percentage points**, not −18.75% of the original cash/time objective.
This shows a business PASS and a deterioration watch can coexist.

The five Evaluation starts are January 1, February 17, April 3, May 19 and July 3,
2026. Actual chronological funding times are **6,20,5,21,5 calendar days**.
Each purchases one $99.50 Evaluation. For the January start, the first target is
reached Monday January 5; further trading meets 50% consistency Tuesday January 6;
Funded readiness is Wednesday January 7: six elapsed days after January 1. The
minimum/median/maximum time is 5/6/21 days. No elapsed time alone satisfies the
consistency rule and no cushion is added.

Funded OOS mean receipts are **$2,812.50**. The cash distribution includes every
zero: P10/median/P90 are **$1,800/$1,800/$5,400**, and **1/16=6.25%** receive no
cash. Conditional first receipt median/P75/P90 are 30/58/65 calendar days among
15 receipt paths. Milestone probabilities count requests and in-horizon receipts
separately, including the unobserved fourth/fifth payout probability of zero.

The five 90-day Funded starts are January 1, March 11, May 19, July 27 and October 2.
Receipts are **$3,600/$1,800/$3,600/$0/$3,600**; each full receipt is
`$2,000 gross × 90% = $1,800`. The March 11 window cuts off June 9: its second
request on June 8 has a two-calendar-day modeled receipt on June 10, so **$1,800
is pending**, not received. The July 27 account receives zero and becomes inactive
September 6 after its last source activity on August 7: 30 calendar days. Ranges
retain this zero (cash min/median/max $0/$3,600/$3,600). No replacement account
starts after inactivity. Chronology uses saved signals with declared costs.

`verify_outputs.py` independently sums fees, dates and cash events, computes
quantiles/zero counts without production code, checks the exact start outcomes,
and verifies the account-start report retains byte-equivalent MC path data.
The API tests also poison the MC optimizers during re-review/start jobs, preserve
sealed historical report fingerprints, reject changed declarations/code/evidence,
and exercise retrospective policy application. Unit oracles retain finite-limit,
equality/failure/inconclusive, full-window, censoring and pending-cash boundaries.

## Saved artifacts

- `verification.json`: normal browser journey IDs/settings and completed jobs.
- `independent-verification.json`: independently computed arithmetic, chronological
  outputs and all numerical source hashes; `verify_outputs.py` reproduces arithmetic.
- `evaluation-oos-*`, `funded-oos-*`: actual sealed report JSON and evidence ZIP.
- `*-account_starts-*`: actual report JSON and ZIP for start sensitivity.
- `*-economic-assessment.png`, `*-account-starts.png`: inspected desktop UI.
- `variant-configuration.png`, `validation-mobile.png`: setup and responsive UI.
- `sha256.json`: immutable evidence checksums (the final index excludes itself).

Rule choices remain exact consistency without a cushion, fixed $1,200 enabled
DLL above the profit threshold, and 30-calendar-day Lucid inactivity. Their local
assumption status remains explicit. Portfolio allocation and full replacement
cash-flow analysis are separate future increments.
