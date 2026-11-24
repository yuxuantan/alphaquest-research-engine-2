# Exact OOS refit acceleration — 2026-11-14

This is saved evidence from the actual AlphaQuest product, plus separate
read-only numerical comparisons. Synthetic product sources are labeled in each
journey. No fixture predicts future results or establishes provider parity.

## What changed

- Internal historical refits capture means/required precision rather than unused
  per-attempt/payout-event dictionaries, quantiles and inner schedule hashes.
- Worker-local civil calendars and exact immutable MT19937/PCG64 prefixes are
  prepared once, within a 32 MiB accounted budget. Long tails and budget misses
  retain the original streams and all accounts.
- Lucid calendar acquisition and Apex renewal use their matching compiled owner
  source. The Python reference remains supported; native percentage-risk session
  execution keeps its existing owner. Funded compact refits call the existing
  account class with no detailed payout capture.
- Completed outer refits checkpoint in the existing catalogue, batch at most once
  per second and flush at cooperative exit. Compatible retries restore only
  verified completed indices. Partial work cannot publish a verdict.
- Prop Sim and Job history show the restored count; rate/ETA count new work only.

All 10,000 outer refits, requested inner paths, frozen candidates, original guards,
costs, seeds and statistical checks remain. Full IS/OOS point paths and downloadable
source evidence are retained. Numerical identities change honestly; old freezes
remain historical and reject new-owner launch. Pre-update running jobs have no
retroactive checkpoints.

## Inspect actual product results

For each account, open `apex-50k-eod/` or `lucidflex-50k/`:

- `configuration.png`, `journey.json`, `simulation.json`: the normal report →
  Prop Sim → one Run configuration and automatic selections.
- `evaluation-is.json`, `funded-is.json`: the actual IS outputs.
- `evaluation-oos.zip`, `funded-oos.zip`: sealed full report, historical bootstrap,
  qualification policy, source captures, account paths and normal downloads.
- `*-summary.json`, `*-complete.png`, `mobile.png`: the ordinary results UI,
  compact summaries and narrow-screen result.

Independent synthetic constant-day expected outcomes at 9 MNQ, eight paths:

| Account | Evaluation acquisition cost | Fresh Funded 90-day mean receipts |
| --- | ---: | ---: |
| Apex 50K EOD | USD 178 = 49 purchase + 129 activation | USD 13,000 |
| LucidFlex 50K | USD 80.50 | USD 9,000 |

OOS qualification retains 10,000 ordered refits per phase. All IS/OOS ratios and
bounds are one on this constant-day fixture, so historical GO opens forward
review PENDING. The existing independent payout ladders explain the Funded cash
oracles; this does not fabricate live-account cash or forward execution.

`resume/` contains a separate normal Stop → Retry journey, both progress-page
screenshots and the sealed resumed report. Expect a positive restored-refit count,
all indices 0–9,999 exactly once, the same constant-day cost and historical GO.
Successful publication clears that attempt's operational checkpoint rows. Stopped
attempts retain their rows until deleted; abrupt death can lose the uncommitted
batch and restarts an unfinished refit from its index.

## Independent numerical comparison

`independent-verification.json` records exact equality of **20 real-source refits**
with 1,000 inner accounts for each IS/OOS history, plus **78 full-capture boundary
cases**, against the preceding `dda9399` implementation. Raw metrics, errors,
source-index hashes, ratios and timings are in `benchmark-{baseline,accelerated}.json`.
Full path/fee/date/censoring/schedule outputs are in
`full-capture-{baseline,accelerated}.json`.

Warm serial sample medians show Apex Evaluation 3.84×, Lucid Evaluation 2.75–6.50×,
and Funded 1.45–1.61× speedups. Each uses three refits after one cold preparation
call. The live machine had other running work. These are small samples, not a
controlled capacity experiment, a complete real-data 10,000-refit qualification,
or guaranteed whole-workflow runtime. Cold preparation is included in the raw
files and may take longer than the old first refit.

The four-worker default remains. Six workers can be declared through the existing
`ALPHAQUEST_PROP_WORKERS` setting within Runtime capacity; earlier measurements
showed modest scaling, so this change does not silently increase live contention.

## Reproduce

Build the matching optional kernels once:

```sh
.venv/bin/python setup.py build_ext --inplace
```

Run only the affected backend surface:

```sh
.venv/bin/python -m pytest -q \
  tests/test_prop_refit_acceleration.py \
  tests/test_lucid_calendar_acquisition.py \
  tests/test_funded_preparation.py \
  tests/test_prop_confidence_parallel.py \
  tests/test_native_prop_compiled.py::test_compiled_model_matches_every_reference_account_and_rng_result
```

Run the normal product journeys (temporary servers stop at fixture teardown):

```sh
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome \
.venv/bin/python -m pytest -q \
  tests/test_prop_sim_automatic_browser.py::test_one_run_finishes_all_four_simulations_after_navigation \
  tests/test_prop_confidence_parallel_browser.py::test_stop_retry_restores_completed_refits_in_both_progress_pages
```

With the corresponding saved real source/report IDs present, reproduce the small
read-only comparison. Use a separate source checkout for `dda9399`; keep the live
workspace/server unchanged. Run scripts from each checkout so imports use its
owner. `benchmark_refits.py` reads saved real sources at
`ALPHAQUEST_REFIT_SOURCE_ROOT` (defaults to this user's workspace), and writes only
the explicitly chosen evidence file.

```sh
.venv/bin/python docs/evidence/qualified_prop_sim/refit-acceleration/benchmark_refits.py /tmp/aq-refits-current.json
.venv/bin/python docs/evidence/qualified_prop_sim/refit-acceleration/full_capture_oracle.py /tmp/aq-full-current.json
```

Verify every baseline/accelerated replicate and full output object with exact
JSON equality, excluding elapsed-time/preparation diagnostics. Preserve raw cold
and warm timing samples; avoid extrapolating them into a claimed completed job.

Backend tests additionally cover Python/compiled and compact/full equality,
cold/warm and zero-budget sampling, long RNG tails, partial checkpoint retry,
changed input separation, corruption rejection, deletion cleanup, parallel stop
and pool reuse. The product retry journey confirms the same flow without a new
page, API, scheduler or second result store.

## Applied workspace and live restart

The user authorized application and restart after the isolated checks. The
implementation is now applied on `epic/revamp-workflow`; both matching compiled
kernels were rebuilt, and all **49 focused backend/calendar checks** pass in this
workspace. The three isolated normal-product browser journeys above passed.

The old simulation `3444051a2ad94a709a39b362115792c3` was cooperatively stopped.
A new automatic simulation uses exactly the same configuration apart from its
request ID: [open the replacement run](http://127.0.0.1:8000/#prop-sim?analysis=f0c73356f2f140b6ac22ebeed2e6ee82).
It retains 1,000 paths per size/phase, all 10,000 historical refits, seed 42,
five-weekday blocks, LucidFlex 50K 50% consistency, and independent 1–40 MNQ ranges.
Existing numerical freezes/reports remain historical; the new implementation
builds a fresh phase package rather than bypassing their guards.

`live/` records the normal source check, original/replacement configurations,
cooperative stop, six unchanged historical report/ZIP seals, launch/progress
verification and read-only portal screenshots. The recorded status is a launch
snapshot, not a claim that the full real-data qualification has finished.

The persistent portal is at `http://127.0.0.1:8000`, PID **41520**, launched with
`/bin/sh scripts/serve_portal.sh`. Stop it with `kill 41520` (this interrupts any
active work); prefer the portal's normal Stop control before server maintenance.
All isolated test servers have exited.
