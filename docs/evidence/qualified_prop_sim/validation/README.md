# Qualified Prop Sim: account variants and frozen validation — 12 November 2026

This evidence comes from the **normal product**, using a labeled synthetic NQ
source qualified through mechanics, Broad, Narrow, OOS and full-period Monte
Carlo. No actual user simulation, dataset or historical report was changed.
AlphaQuest performs every calculation locally; Bridge is not invoked.

## Reproduce

From the repository root:

```sh
ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR=/private/tmp/prop-validation-reproduction \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey
```

The browser fixture starts an isolated temporary server/catalogue, executes the
complete existing source -> check -> run -> saved-results journey, and stops
that server at teardown. Evidence IDs are from that isolated catalogue and are
not live links into the user's library. The synthetic $99.50 purchase price is
an explicit example input, not a provider quote. The sixteen-path demonstration
is an inspectable mechanics example, not a precise sizing recommendation.

The browser selects LucidFlex 50K, explicitly chooses the 50% add-on and enters
its scenario fee; changing consistency clears the fee instead of assuming an
add-on price. Evaluation searches 12/13 MNQ and Funded searches 12 MNQ. The
50% choice changes only Evaluation's profile and identity; Funded has no
consistency gate and remains independent of evaluation fees and timing.

## Expected actual observations

- `variant-configuration.png` shows the real configuration/check form.
- Evaluation's initial 16 paths at each size have mean cost **$99.50** and mean
  funding time **13.875 calendar days** (13.88 displayed). Every path purchases
  one account. The independent arithmetic is total fees / 16 and total elapsed
  days / 16; no fee/pass shortcut is used for Lucid.
- The time breakdown is **0 + 9.4375 + 2.9375 + 1.5 = 13.875 days**: earlier
  attempts, final account to first target, further trading after target, and
  funded readiness. Both sizes tie exactly in this small demonstration; paired
  differences retain both points rather than inventing a winner.
- Funded's initial mean receipts are **$2,475.00 = $39,600 / 16**, including every
  zero-receipt path. Its **$112.50** mean pending cash is separate from receipts.
- The user explicitly freezes one size per phase with a rationale. The download
  contains immutable candidate IDs, sizes, rules, fees, sampling, source identity,
  code hashes and prior access. Frozen checkboxes cannot change.
- Each phase then runs three separate saved assessments: OOS, IS robustness and
  increased precision. Each assessment has **no winner and no reselection**;
  every row retains the selected frozen candidate ID. Original IS reports and
  frozen hashes remain unchanged.
- OOS Evaluation has **23.25 mean calendar days** and **$130.59375 mean cost**
  under its unchanged frozen MC settings. The separate actual-order OOS replay
  acquires funding in **6 calendar days for $99.50**. This is one chronological
  observation, not another estimate of mean acquisition time.
- OOS Funded has **$2,812.50 mean receipts**. Its separate chronological fresh
  account receives **$3,600** over the frozen 90-day horizon: two modeled gross
  $2,000 withdrawals at the saved 90% trader share. It remains open at cutoff;
  no replacement account or acquisition costs enter it.
- Robustness publishes five rows per frozen size: full IS with blocks **1, 5,
  20**, then its first and second weekday halves using the original block. It
  uses the explicitly requested **8 paths**, with actual scenario configurations
  and source periods saved. These are sensitivity measurements, not new gates.
- Precision publishes **64 paths** per frozen size, with source, size, account
  options and seeds unchanged. It refines estimates without overwriting the
  original 16-path IS decision/report or redefining the OOS package.
- Each assessment appears in Job history and links back to this Prop Sim. The
  portal supplies a report JSON and evidence ZIP; reload restores all histories.
  `validation-mobile.png` verifies the real 390-pixel layout without page overflow.

`verification.json` records identifiers, frozen choices, per-phase studies and
baseline metrics. `*-baseline-report.json`, `*-oos-report.json`,
`*-is_robustness-report.json`, `*-precision-report.json`, and the matching six
`*-evidence.zip` files are actual sealed product outputs. Screenshots show both
phase sections. Source exports, scenarios, paths and frozen packages can be
inspected in the normal evidence ZIPs; no duplicate result database is created.

## Independent arithmetic and rejection checks

```sh
.venv/bin/python -m pytest -q tests/test_lucid_calendar_acquisition.py \
  tests/test_prop_evaluation_validation.py tests/test_prop_sim_deletion.py
```

Independent deterministic fixtures are kept in tests, not in the product UI:

- $1,500/day passes 50% on day two and 40% on day three; next-session readiness
  gives 2 versus 3 elapsed calendar days from a Monday purchase.
- An account that hits $3,000, is blocked by consistency, then breaches on an
  observed gap must pay for its retry. Three subsequent $1,000 days produce a
  Friday pass/Monday readiness: **7 days, two fees = $161**, with one failed
  after-target account. Its components are **2 + 2 + 0 + 3 = 7 days**.
- A computational guard is distinguished from the exclusive chronological OOS
  source boundary. Open paths never acquire a fabricated finite mean.
- Paired identical paths produce exact zero differences; constant ten-day/eighty-
  dollar differences produce exact nonzero intervals without changing membership.
- Arbitrary 52% variants, omitted 50% fees, assessments before freezing, changed
  frozen decisions, insufficient precision paths and incompatible numerical code
  reject. Shared/source deletion protection remains covered by existing tests.

## Use in the portal

1. From a qualified IS source report, open **Configure prop analysis** / Prop Sim.
2. Select the actual account variant and purchase fee, check, then run.
3. Inspect mean/median/P90, funding probabilities, time components, MC uncertainty
   and paired differences. Exact/approximate statistical comparisons do not
   certify future performance or provider parity.
4. In each phase's **Freeze choices and validate**, select up to four eligible
   sizes, enter a rationale, and freeze. Evaluation permits resolved Pareto
   points; Funded permits feasible ranked points. The phases remain independent.
5. Use **Assess frozen sizes on OOS**, **Check IS blocks and subperiods**, or
   **Run more paths for frozen sizes**. Diagnostic paths are explicit. Resource
   limits reject oversized requests instead of silently dropping candidates.
6. Follow progress here or in Job history, stop active assessments if needed,
   and download/reopen their durable reports. Manual assessment history is
   append-only and does not rerank or replace the original choices.

OOS was already accessed in campaign qualification; the page explicitly says
this is not an untouched holdout. Historical reports remain readable. Numerical
source hashes change for this increment, so old packages cannot silently execute
with new code: start a **new simulation** for current freeze/validation tools.
No account-aware strategy rerun, daily winner clipping, live returns, portfolio
allocation, or new automatic OOS acceptance threshold is introduced.
