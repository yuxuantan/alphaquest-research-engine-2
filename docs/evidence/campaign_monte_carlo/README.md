# Final full-period Monte Carlo evidence

This folder preserves the original **v1** policy and evidence. Current v2 removes
the drawdown rejection gate and adds descriptive metrics; see [v2/README.md](v2/README.md).

The synthetic source and downloaded artifacts in this directory come from the
normal dataset → mechanics → IS Broad → IS Narrow → OOS → final sanity check
workflow. They are not market evidence, measured MultiCharts parity, or a claim
of future profitability. Earlier OOS evidence is unchanged.

## Reproduce in the portal

1. Start the existing application: `.venv/bin/uvicorn alphaquest.app:app`.
2. Open `http://127.0.0.1:8000/#campaigns`, choose a validated dataset workflow,
   confirm its IS selections and complete OOS. Up to four candidates can pass.
3. On the OOS page, read **Final Monte Carlo sanity check** and its three rules.
   Click **Run final Monte Carlo check**. Only verified OOS-passing candidates
   enter; a pending OOS batch or one with no passing candidates cannot launch it.
4. Navigate to **Job history**, filter **Final Monte Carlo checks**, and use
   **Open final Monte Carlo check**. The worker continues after navigation.
   Both pages display the saved candidate/block/path progress. **Stop Monte
   Carlo** cancels at a batch boundary; another explicit launch uses the same
   seed and policy rather than rerolling for a better result.
5. Expect two rows per admitted candidate (mean blocks 5 and 20). Each must pass
   the evidence rule and both tail checks under both block settings. The combined
   verdict is separate from OOS. The four-phase navigation and frozen IS choices
   stay intact. Read the daily-close/intraday and reused-data limitations.
6. Download JSON, evidence ZIP, full-period daily P&L and simulated path outcomes.
   Reload or restart the application: the identical sealed report reopens,
   with no strategy replay or repeated bootstrap. An unchanged completed check
   is reused. Edited artifacts fail the integrity check rather than passing.
7. Stop a server you started with Ctrl-C. The test below shuts its temporary
   server down automatically and does not restart the user's existing server.

## Independent expected outcomes

`SYNTHETIC-source.csv` has 120 IS and 60 OOS active dates. Each produces six
closed trades, 12 gross price points × 10 CU/point, minus 30 CU slippage and
12 CU commissions = **78 CU/day/contract**. The complete period therefore has
**1,080 trades and 14,040 CU** per one-contract candidate, **28,080 CU** at two
contracts. Inactive observed dates are also retained, with zero net P&L.
No costs are subtracted a second time. Every daily increment is nonnegative in
this synthetic example, so every resampled daily-close drawdown is exactly zero;
the historical daily-close drawdown and its limit are also zero. All four
candidates pass, with 10,000 paths each (5,000 per block setting). Net profit is
not held fixed by shuffling: it varies because blocks are sampled with replacement.

Fast independent boundary checks additionally establish:

- 100 observations of +2.50 CU give exactly +250 CU and zero drawdown in all
  10,000 paths. The same history with only 99 closed trades is insufficient.
- 100 observations of −1 CU give exactly −100 CU and 100 CU drawdown, and fail.
- 99 observations of −1 followed by +200 have historical profit +101 CU but
  negative 5th-percentile profit under both block settings, and fail.
- Alternating +10/−1 for 100 observations has +450 CU historical profit and
  1 CU drawdown. The seeded 5-day block scenario has 3 CU tail drawdown and
  fails its 2 CU limit despite positive lower-tail profit. The 20-day scenario
  equals the limit at 2 CU and passes, proving inclusive drawdown handling and
  the requirement to pass both block settings.

## Exact automated reproduction

```sh
.venv/bin/python -m pytest -q tests/test_monte_carlo.py tests/test_campaign_monte_carlo.py
ALPHAQUEST_MC_EVIDENCE_DIR=/tmp/alphaquest-mc-evidence .venv/bin/python -m pytest -q tests/test_campaign_monte_carlo_browser.py
```

The browser journey creates its synthetic source through the ordinary dataset
API, freezes real native IS selections, executes real OOS reports, starts Monte
Carlo from the actual OOS page, leaves for job history, returns, downloads, and
reopens without recalculation. `journey.json` identifies the generated records.
`report.json` records source/artifact hashes, full settings, NumPy and calculation
identity, windows, raw outcomes and pass/fail reasons. `daily.csv` is the exact
input; `paths.csv` contains the 40,000 path outcomes. `analysis.zip` seals these
ordinary product downloads together; no separate evidence service is involved.
