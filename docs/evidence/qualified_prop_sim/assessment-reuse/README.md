# One current OOS result and lazy history — 2026-11-13

Actual normal-product evidence from an isolated temporary library and Chromium
journey: existing qualified backtest → Prop Sim → configure/check/run both IS
phase workers → freeze Funded size → run qualification → reopen the saved result
→ optional policy revisions → inspect one historical result → download/reload.
All market data are explicitly **SYNTHETIC**; no future performance, provider
parity, real paper execution or live trading is claimed. The temporary server
stopped at teardown. No user library, running job, server or Windows VM changed.

## Inspect the outputs

- `current-result.png`: one current OOS table, **View OOS results**, collapsed
  criteria/per-size checks and compact history. IS sizing collapses after freeze.
- `history-on-demand.png`: one explicitly opened historical assessment.
- `mobile.png`: the same saved workflow at a 390-pixel viewport.
- `qualification.json`, `qualification.zip`: actual normal report/download,
  including source captures, frozen identity, account paths and bootstrap trace.
- `business-pass.json`, `business-fail.json`: different saved business-limit
  assessments over the same OOS account paths. Earlier verdicts remain unchanged.
- `journey.json`: normal simulation/job IDs, observed fetch counts and assertions.
- `unchanged-implementations.json`: all 33 phase numerical sources match their
  existing hashes. Qualification, forward and business-review owners are unchanged.

The demonstration uses the [earlier saved synthetic input](../oos-confidence/apex-50k-eod/SYNTHETIC-source.csv),
strategy `consecutive_green_hold`, green count 3, hold 16 minutes and one original
NQ contract. Prop configuration uses Apex 50K EOD, ten MNQ in each independent
phase, eight account paths, seed 42, five-weekday blocks, 2026-11-16 scenario
start, 90-day Funded horizon, two-day receipt delay and $0.51/MNQ/side commission.
These are analytical fixture settings, not recommended trading sizes or forecasts.

## Independent expected observations

The constant synthetic daily history gives Funded receipts of $13,000 on every
account path. Therefore:

- Reopening the qualification has the same `request_id`/`analysis_id`, creates
  **zero** additional jobs or history rows and preserves the original report.
- A business minimum of **$1** passes; a revised minimum of **$999,999** fails.
  Both reviews must contain **identical account paths**, with mean receipts still
  $13,000. Changing the limits never runs new account simulations.
- There are exactly **three** assessments: one qualification plus the two truly
  different business policies. The rejected duplicate is not a fourth record.
- Initial page load fetches **one** current Funded report. Expanding the history
  list fetches none. Opening one historical entry raises the count to **two**;
  the other historical table remains unloaded.
- The current qualification is GO for historical review and forward execution
  stays PENDING. Business-policy verdicts remain their own assessments.

Verify the saved output without invoking any engine:

```sh
.venv/bin/python scripts/verify_prop_assessment_reuse_evidence.py
```

Expected: mean receipts 13000, limits 1/999999, PASS/FAIL, identical paths, one
current table and one initial report fetch. The downloaded ZIP's report must
match `qualification.json` exactly.

## Reproduce through the portal

1. Open an existing fully qualified IS backtest and follow **Prop Sim**.
2. Choose account/ranges/settings, **Check source and settings**, then **Run
   Evaluation and Funded**. Select eligible IS sizes and freeze with a rationale.
3. Click **Run OOS qualification** once. While running, use **View assessment
   progress**; when complete, the action becomes **View OOS results**. Repeated
   clicks or another tab reopen the canonical result.
4. Reload. IS sizing, qualification rules, per-size checks, history and diagnostics
   remain collapsed by default; one current OOS table is shown per phase.
5. For a genuinely different business policy, expand **Additional diagnostics →
   Optional business limits and historical policies**, declare/revise limits and
   run its assessment. The main qualification stays visible. Previous policies
   appear under **Assessment history**. Open only the version you wish to inspect.
6. Inspect/download its original report and close history to return to the single
   current table. Nothing is deleted or relabeled.

Automated normal-product reproduction:

```sh
.venv/bin/python -m pytest -q tests/test_prop_sim_assessment_reuse.py
ALPHAQUEST_PROP_REUSE_EVIDENCE_DIR=/private/tmp/aq-prop-reuse-evidence \
  .venv/bin/python -m pytest -q tests/test_prop_sim_assessment_reuse_browser.py
```

The tests normally create the synthetic source through the ordinary qualification
APIs. `ALPHAQUEST_QUALIFICATION_SEED_LIBRARY` can optionally name an isolated copy
of an already-created synthetic test library; each test clones it first. The
captured run used this setup optimization. Do not point it at a user library.

Focused API boundaries include eight concurrent requests for a completed result
and eight for a paused running review, all with different request IDs; each group
returns one canonical job with no new rows. Tampered evidence rejects; stopped
attempts remain retryable. Revised limits produce new verdicts while MC owners
are poisoned to prove they are not called. An existing two-phase revision test
also verifies that a running review keeps its captured policy while another
revision is saved. Existing reports and forward references are preserved.
