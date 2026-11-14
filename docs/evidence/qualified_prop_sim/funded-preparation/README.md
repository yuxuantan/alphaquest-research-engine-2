# Bounded Funded preparation reuse — 2026-11-14

Production implementation and normal-product evidence for the measured Funded
historical-refit bottleneck. Earlier evidence is preserved. The browser libraries,
prices and market dates in these product examples are **SYNTHETIC**, including
future-dated example bars. They demonstrate arithmetic and integration, not future
performance or provider parity. Real-source timing/parity is a separate audit.

## Implementation

`DatedFundedPreparation` in `alphaquest/prop/funded_profiles.py` retains immutable
calendar rows and int32 sampled-index buffers. `oos_bootstrap.py` creates one
preparation object per loaded Funded worker context and passes it through
`oos_qualification._means` into the same dated owner. No numerical result is
reused across different historical daybooks.

The cache accounts at most 32 MiB per worker for its entries, keys and owned data.
It keeps admitted prefixes and falls back to the original sampler when more
entries cannot fit. There is no eviction cycle, path clipping, seed change,
historical-replicate reduction or alternative account engine. The worker's most
recent context remains until another context is loaded or its pool closes.
The ordinary one-off dated path also reuses calendar rows within its call, while
its random stream stays lazy. Chronological replay never uses cached random draws.

New normal Funded OOS downloads include
`calculations.qualification_bootstrap[].execution.funded_preparation`, with
version, the per-worker budget and maximum observed accounted bytes. This is
execution metadata, not an eligibility criterion. The four-worker default remains.

## Inspect the normal product outputs

Each profile subfolder contains configuration/results/mobile screenshots,
`simulation.json`, `journey.json`, both IS reports, OOS presentation summaries,
and the normal sealed Evaluation/Funded OOS ZIP downloads. The journey starts at
the saved backtest report and clicks **Run IS and OOS** once; it navigates away
while the existing worker runs and then reopens the durable results.

Independent constant-day expectations:

| Profile | Evaluation acquisition cost | Fresh-Funded cash over 90 days |
| --- | ---: | ---: |
| Apex 50K EOD | $49 + $129 = $178 | Six full caps: $13,000 |
| LucidFlex 50K | $80.50 | Five $2,000 caps × 90% = $9,000 |

All eight requested account paths remain in each mean. Equal point objectives
collapse automatic selection to 9 MNQ, the smaller of the tested 9–10 sizes.
Identical IS/OOS numeric daybooks imply every one of the 10,000 historical ratios
and interval bounds is 1.00; historical qualification is GO and forward execution
remains PENDING. The downloaded cache diagnostics show 30,144 accounted bytes
per worker in these examples, below the 33,554,432-byte limit. A constant-day
example does not establish real-market uncertainty or performance improvement.

Run the independent standard-library verifier, which imports no production
account, sampler, selector or report code:

```sh
.venv/bin/python scripts/verify_funded_preparation_evidence.py
```

Expected: four verified sealed phase downloads, every captured artifact hash and
size matching, eight paths and 10,000 ordered refits each, exact expected cash,
unchanged frozen selection, GO/PENDING and bounded preparation metadata.
The saved result is `independent-verification.json`.

## Reproduce through the portal

Fresh normal workflow:

1. Open a qualified campaign's IS backtest report, then **Prop Sim**.
2. Configure the account, independent Evaluation/Funded sizes and path count.
3. Click **Run IS and OOS**. Source admission, IS searches, selection/freeze and
   OOS continue through the existing AnalysisStore worker without further action.
4. Reopen the simulation and download the Funded **Assessment evidence ZIP**.
   Inspect its `historical_bootstrap.json` execution diagnostics. All requested
   refits/paths remain, including zeros, failures and pending receipts.

Saved exact synthetic libraries are local under
`artifacts/funded-preparation-20261114/libraries/<profile>/`.
For example, reopen the saved Apex demonstration on an isolated port:

```sh
ALPHAQUEST_DATA_DIR="$PWD/artifacts/funded-preparation-20261114/libraries/apex-50k-eod" \
  sh scripts/serve_portal.sh --port 8014
```

Open `http://127.0.0.1:8014/#prop-sim?analysis=<id>` using the `id` in
`apex-50k-eod/simulation.json`. Inspect the source backtest/configuration,
automatic roles and both current OOS tables/downloads. Reload reopens sealed
results without resimulation. Stop this review server with Ctrl+C.

The automated reproduction is the existing
`tests/test_prop_sim_automatic_browser.py` journey for both profiles. It supports
`ALPHAQUEST_PROP_AUTOMATIC_EVIDENCE_DIR` for downloads/screenshots and
`ALPHAQUEST_PROP_PREPARATION_SAVE_LIBRARY` for saved isolated libraries. A
prepared synthetic library can be cloned through
`ALPHAQUEST_QUALIFICATION_SEED_LIBRARY`. Tests create and stop temporary servers;
they never submit work to the user's port-8000 server.

For the exact local reproduction with installed Chrome (or omit the channel
setting when Playwright Chromium is installed):

```sh
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome \
ALPHAQUEST_QUALIFICATION_SEED_LIBRARY="$PWD/artifacts/funded-preparation-20261114/libraries/apex-50k-eod" \
ALPHAQUEST_PROP_AUTOMATIC_EVIDENCE_DIR=/private/tmp/aq-funded-preparation-reproduction \
  .venv/bin/python -m pytest -q tests/test_prop_sim_automatic_browser.py
```

## Exact real-source parity and measured performance

`real-source-qualification.json` compares the implementation to the captured
preceding dated Funded owner. Its source hash matches the original real Funded
report's recorded owner hash. It verifies 12,000 full path records, events,
account rules and schedule hashes on both 13/14-MNQ sizes, both IS/OOS books, and
the original/outer-0/outer-9,999 histories. Sampled complete refit metrics,
MC errors and index hashes also match the original saved bootstrap rows exactly.

Three interleaved eight-refit trials per variant, with 1,000 paths per history:

| Size | Prior median | Implemented median | Speedup |
| --- | ---: | ---: | ---: |
| 13 MNQ | 4.227 s | 1.655 s | 2.55× |
| 14 MNQ | 4.171 s | 1.581 s | 2.64× |

Cold first-refit cost is retained separately in the JSON. Real-input preparation
used 1,553,792 accounted bytes per worker. Projecting these measured ratios onto
the earlier saved run gives about **24 min 20 s Funded confidence** and
**44 min 23 s overall**, versus 63 min 06 s and 83 min 09 s. This is a sample-based
projection; no full optimized real-data 10,000-refit report is claimed.

Local reproduction of that read-only audit:

```sh
.venv/bin/python artifacts/funded-preparation-20261114/qualify_implementation.py
```

This audit uses the original real saved simulation as a source/oracle and writes
only audit evidence. It does not create another production job or select sizes.
The prior source snapshot remains an immutable qualification reference.

## Boundaries, checks and live application

The 46 focused backend checks cover exact scalar MT19937 prefixes, immutable
buffers, zero/tiny/oversized budgets, streaming fallback without truncation,
changed calendar closures/versions, both account profiles, closed-date inactivity,
pending receipts, chronological coverage, cancellation and worker budget drain,
normal independent Funded APIs, source protection and numerical identity guards.
The full qualified pipeline API check passed separately, and both actual browser
journeys passed: 49 focused cases across these final checks. `backend-tests.xml`
records the 46-case run.

This numerical-owner change is included in the real phase implementation hashes;
no changed calculation file was excluded and no compatibility bridge was added.
New qualification identities also include the new dispatcher/means code. Older
frozen Funded packages cannot launch under the new owner; their reports/ZIPs
remain readable and unchanged. Start a new simulation for accelerated numerical
runs rather than rewriting old freezes or qualification verdicts.

The idle live portal was gracefully restarted using the stable file-logging
launcher, from PID 26317 to PID 28156. No job was active. All four original real
IS/OOS reports and ZIP seals match before/after. Live APIs and browser work; the
original source remains selectable, and the older Funded numerical package is
explicitly marked incompatible for another launch. See `live-application.json`
and `live-verification.json`. The source picker took about 0.85 seconds and the
actual Prop Sim form was usable in about one second.

All test-owned temporary servers/process pools stopped. The user portal remains
intentionally running on port 8000, PID 28156. Stop this instance with
`kill -TERM 28156` when no job needs to finish. Existing reports and their verdicts,
the Windows VM and unrelated user processes were preserved.
