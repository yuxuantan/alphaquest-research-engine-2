# MultiCharts OHLC execution delivery — 2026-11-16

All price sources here are labeled synthetic. Reports/downloads came from the
normal Dataset → Campaign → Mechanics → IS Broad → Backtest report workflow
in a temporary isolated library. No synthetic campaign was inserted into the
user's data library. Temporary review servers were stopped after capture.

- `product/verification.json`: expected cash, actual model comparison, download
  hashes, durable unchanged report reopen and no browser errors.
- `product/entry-protection-sensitivity.png`: actual report panel; primary -52,
  High-first 338, Low-first -52 on the same OCO entry bar.
- `product/inconclusive-sensitivity.json`: primary completes; alternate path
  holds across a missing closing bar and remains inconclusive without a fake total.
- `core/verification.json`: C#5 compilation, 11 state/order cases (18,923 bars),
  18 independently C#-driven full replays with exactly matching events.
- `core/*-events.json`: complete trade, equity and modeled held-risk events.
- `core/*-independent.jsonl`: C# decisions/protection plans in each full replay.
- `historical-reader-verification.json`: original v1/v2 sealed artifact hashes
  verified against the new reader, without mutation.
- `SHA256.json`: checksums of the saved outputs. Large flat random-case traces
  stay in the temporary review directory; the reproducible seed/code and case
  counts are preserved in the harness and verification summary.

Read [the execution contract](../../docs/multicharts_execution.md) for official
MultiCharts sources, model assumptions, limitations and commands. Reproduce with:

```sh
PYTHONPATH=.:tests .venv/bin/python tests/review_twin_csharp.py \
  --dotnet /path/to/dotnet --output /tmp/aq-multicharts-core-review
PYTHONPATH=.:tests ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python \
  tests/review_entry_protection.py --output /tmp/aq-multicharts-product-review
```

The second command uploads `SYNTHETIC-twin-campaign.csv`, performs a synthetic
mechanics attestation, runs two Broad trials with the normal worker, opens the
report and downloads/reopens evidence. Such a fixture attestation does not
establish measured MultiCharts parity. Installed SDK/native fills/live execution
are unverified. Historical reports keep their original assumptions and verdicts.
