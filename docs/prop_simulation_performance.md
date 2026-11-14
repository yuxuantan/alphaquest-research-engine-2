# Prop Sim runtime analysis — 2026-11-14

Scope: the saved Apex simulation `ede834c9fea44f2fa663e481dd8d4582`, with 60
Evaluation sizes, 40 Funded sizes, 1,000 inner paths, five-session blocks,
10,000 historical refits per frozen size and a 90-calendar-day Funded horizon.
The initial analysis below records the isolated prototype. The implementation
was subsequently delivered and applied; see the delivery section at the end.

## Where the time went

The parent was saved at 08:34:30.791 Singapore time; the last report ZIP finished
at 09:57:39.381. Total approximately **1 h 23 min 09 s**.

| Work | Time | Basis |
| --- | ---: | --- |
| Evaluation IS search, sizes 1–60 | 1 min 07 s | Enqueue to ZIP publication; approximate execution interval |
| Funded IS search, sizes 1–40 | 1 min 00 s | Previous worker job's ZIP to this ZIP; approximate execution interval |
| Evaluation historical OOS confidence, three frozen sizes | 17 min 23 s | Sum of directly saved bootstrap execution durations |
| Funded historical OOS confidence, two frozen sizes | 63 min 06 s | Sum of directly saved bootstrap execution durations |
| Remaining setup, admission, base OOS work, freezing and publication | About 33 s | Residual; these substages were not individually instrumented |
| Total | 1 h 23 min 09 s | Parent timestamp to final ZIP publication |

Historical confidence consumes **96.8%** of the total; Funded confidence alone
consumes **75.9%**. IS search is only about 2.6%. Normal portal loading and the
previous terminal-output outage are separate from these numerical runtimes.
The refit workers continued while the web thread was blocked.

Saved per-size confidence durations, all with four active workers:

| Phase / size | Refit wall time |
| --- | ---: |
| Evaluation 48 MNQ | 4 min 35.83 s |
| Evaluation 27 MNQ | 6 min 54.18 s |
| Evaluation 46 MNQ | 5 min 52.53 s |
| Funded 13 MNQ | 33 min 37.18 s |
| Funded 14 MNQ | 29 min 28.45 s |

Do not treat `created_at_utc` as execution start: it is the enqueue timestamp.
For example, Funded OOS was enqueued at 08:37:00.724, but waited behind Evaluation
until approximately 08:54:29.017. Its enqueue-to-finish time is 80 min 38.66 s,
including about 17 min 28 s of queue wait. Counting that wait again would inflate
the total. Individual source-check/report-publication timings cannot be recovered
exactly from the existing metadata; the residual above is not a fabricated profile.

## Why the historical confidence stages are expensive

Every outer historical replicate refits both the IS and OOS history using the
full requested inner path count. For Funded:

`2 sizes × 10,000 outer replicates × 2 histories × 1,000 accounts = 40 million account paths`.

Evaluation runs 60 million first-attempt paths plus 60 million acquisition chains
across its three sizes. Its attempt arithmetic already uses the compiled Apex
kernel, whereas dated Funded refits run the Python account/calendar owner.
There is no report-time substitution for a sampled account path.

The historical memoization keys show 10,000 distinct IS and 10,000 distinct OOS
histories per Funded size. Reusing whole historical answers therefore offers
little benefit on this source. But the inner per-account random stream depends
on the fixed seed, path index, daybook length and block length, not the resampled
daybook's contents. The same index prefixes are regenerated thousands of times.
Calendar dates/open-session flags are similarly rebuilt for every account.

Representative real-source cProfile runs reproduced saved bootstrap rows exactly:

- Funded: account advancement accounted for about 43% of profiled cumulative
  time; the dated owner also spent substantial time on date handling, RNG
  initialization and schedule construction. Four profiled refits made about
  8.6 million Python calls.
- Evaluation: `acquisition_metrics` accounted for about 85% of profiled time;
  the compiled attempt calculation was about 12%. Optimizing only the attempt
  kernel would miss most of the remaining Evaluation cost.

These are instrumented attribution samples, not end-to-end speed estimates.

## Measured first optimization: reuse immutable preparation

An isolated copy of the dated Funded owner reuses fixed sampled-index prefixes
and calendar tables. It retains the original account transitions, float arithmetic,
receipt cutoffs, source histories, seeds and all 1,000 requested paths. A terminated
account consumes the same prefix as before; unused prefetched draws have no effect
on other independently seeded accounts. No historical account result is cached
across different histories.

Interleaved baseline/cache trials used both frozen Funded sizes, eight real
historical refits per trial, three alternating-order trials, and medians:

| Size | Original, eight refits | Reused preparation | Speedup |
| --- | ---: | ---: | ---: |
| 13 MNQ | 4.218 s | 1.870 s | 2.26× |
| 14 MNQ | 4.070 s | 1.757 s | 2.32× |

The tested replicate metrics, relative MC errors and source-index hashes match
their original saved rows exactly. Separate comparisons checked **12,000 complete
path records**, including payout events, terminal states, receipt/pending amounts,
schedule hashes and account rules. These covered both sizes, both IS/OOS books,
the original books and outer replicate indices 0 and 9,999.

Applying those measured ratios to the recorded per-size durations projects:

- Funded confidence: approximately **27 min 38 s**, from 63 min 06 s.
- Whole saved workflow: approximately **47 min 41 s**, from 83 min 09 s.

This is a projection from small real-source samples, not a completed optimized
10,000-refit product run or a runtime guarantee. Cold schedule preparation is
reported separately in the evidence. The exploratory compiled-account variant
offered only a modest gain in its first sample; combining every prototype was
noisier and not consistently fastest. Do not multiply those exploratory speedups.

For a production implementation, keep preparation bounded and local to the
existing worker context. Prefer compact integer arrays and an explicit byte
budget, keyed by seed/path count/daybook length/block/horizon and the complete
calendar identity. At this run's 1,000 paths and approximately 64 open sessions,
two int32 IS/OOS index tables require about 0.5 MiB per worker. Larger declared
path counts/horizons need a bounded chunk/cache fallback; never clip paths.

## Worker scaling is secondary

The existing Runtime was tested separately with its original owner, 24 real
Funded refits per trial, two trials after pool warmup:

| Workers | Mean time for 24 refits |
| --- | ---: |
| 4 | 4.029 s |
| 6 | 3.472 s |

Six workers were **1.16× faster**, about 14% less wall time, rather than a 50%
throughput improvement. This host exposes eight logical CPUs; six leaves two
logical CPUs outside this worker group, without assuming equal core performance.
All outputs matched the saved refits. During the bounded test, 86 normal portal
history requests succeeded, with maximum latency about 54 ms. This tests one
metadata endpoint, not every large report/UI journey under sustained load.
The live server's four-worker setting was not changed or restarted.

## Recommended order

1. Implement bounded fixed-index/calendar preparation reuse inside the existing
   dated Funded owner and worker context. Keep one account-transition implementation.
   This is the largest demonstrated low-scope improvement.
2. Optimize Evaluation acquisition preparation and inner-summary allocation,
   guided by the profile. Preserve all chain paths, retry guards, fee timing and
   equal-cohort uncertainty. No measured Evaluation speedup is claimed here.
3. Add durable per-stage queue/start/finish/elapsed timing to the existing
   catalogue/report so admission, simulation, historical refits and publication
   can be distinguished without relying on file mtimes.
4. Consider six workers as an explicit resource setting after sustained portal
   load checks. Do not replace the existing budget with another scheduler or
   increase the web server's application worker count.

Retain 10,000 historical refits, the full inner path counts, all selected frozen
sizes, the horizon, block lengths and fixed seeds. Preserve cancellation and
ordered output. A production numerical-owner change must get its proper new
implementation identity and qualification evidence; old frozen-package guards
must not be bypassed to make old packages launch. Old reports stay unchanged.
Partial benchmark parity is not full numerical/provider certification.

All five existing size qualifications have `inner_precision_ok: false` and remain
`INSUFFICIENT_EVIDENCE`. Speeding up the same calculation does not change that
verdict. An optional early runtime/precision warning could help users understand
cost before launch, but is not permission to truncate the required assessment.

## Evidence and reproduce

All evidence is under `artifacts/prop-sim-performance-20261114/`:

- [Timing reconstruction](../artifacts/prop-sim-performance-20261114/timing-breakdown.json).
- [Funded profile](../artifacts/prop-sim-performance-20261114/funded-profile.txt) and
  [Evaluation profile](../artifacts/prop-sim-performance-20261114/evaluation-profile.txt).
- [Interleaved cache benchmarks](../artifacts/prop-sim-performance-20261114/paired-benchmarks.json).
- [Full path parity](../artifacts/prop-sim-performance-20261114/full-path-parity.json).
- [Worker scaling and actual portal probes](../artifacts/prop-sim-performance-20261114/worker-scaling.json).

From the repository root, run these sequentially to avoid benchmark interference:

```sh
.venv/bin/python artifacts/prop-sim-performance-20261114/profile_refits.py
.venv/bin/python artifacts/prop-sim-performance-20261114/profile_refits.py --phase evaluation
.venv/bin/python artifacts/prop-sim-performance-20261114/paired_benchmark.py
.venv/bin/python artifacts/prop-sim-performance-20261114/check_full_paths.py
.venv/bin/python artifacts/prop-sim-performance-20261114/worker_scaling.py
```

The last script refuses competing active Prop Sim work and probes the existing
port-8000 portal. It closes its own process pools. It creates no product jobs,
new reports or second data store. Existing sources/report seals are preserved.
Four focused compiled/reference account and RNG parity cases also passed via
`tests/test_native_prop_compiled.py::test_compiled_model_matches_every_reference_account_and_rng_result`.

To inspect the actual product outputs, open the original saved simulation in
Prop Sim and download its existing Evaluation/Funded IS and OOS report/ZIP links.
The canonical saved analysis is reused; no new simulation was launched for this
performance audit. Normal product timings and benchmark timings remain distinct.

Primary technical references:
[NumPy parallel random streams](https://numpy.org/doc/stable/reference/random/parallel.html),
[Python process executors](https://docs.python.org/3.12/library/concurrent.futures.html#processpoolexecutor).

## Delivered bounded Funded preparation reuse — 2026-11-14

The first recommendation is implemented in the existing Funded owner and
historical worker context. Immutable calendar/index preparation has a 32 MiB
accounted per-worker ceiling with original-stream fallback, retaining every path
and refit. New report downloads record preparation version/budget/observed bytes.
The four-worker default, account arithmetic and assessment rules remain intact.

The actual implementation matched 12,000 complete prior-owner real-source paths
and sampled saved refit metrics exactly. Interleaved real-source benchmarks gave
2.55×/2.64× at 13/14 MNQ, projecting approximately 44 minutes overall for the
earlier 83-minute job. That projection is not a full optimized real-data run.
Both Apex/Lucid normal automatic browser journeys and independent synthetic cash
oracles pass, alongside 46 focused backend cases and a full qualification API
case. The idle portal was gracefully restarted and all four original report/ZIP
seals remained unchanged. Source/qualification implementation identities capture
the changes; old frozen Funded packages reject new numerical launches without
altering their historical reports.

[Delivery, saved downloads, real-source qualification and exact reproduction](evidence/qualified_prop_sim/funded-preparation/README.md).
Evaluation preparation changes, additional stage timing and a six-worker default
remain separate proposals; they were not activated by this delivery.
