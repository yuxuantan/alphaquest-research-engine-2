# MTM foreground and optional daily-close diagnostics

This presentation update changes no calculation, admission rule, source identity
or saved report. The Monte Carlo table shows frozen IS/OOS bar-close MTM maximum
drawdowns from the existing verified OOS results. Daily-close bootstrap drawdown
measurements move into an optional section collapsed by default. They remain in
saved reports/downloads for comparison on the same daily-sampling basis.

To inspect an existing assessment, open its campaign OOS page and scroll to
**Final Monte Carlo sanity check**. The main results show separate IS and OOS
MTM columns. Expand **Daily-close Monte Carlo drawdown diagnostics (optional)**
to see original/median/95th-percentile daily-close drawdown, its multiple and
historical percentile. The help explicitly distinguishes daily sampling from
every-bar MTM and intraday account-rule risk. No rerun or policy update is needed.

The single affected Chromium journey uses the normal native synthetic campaign
workflow. It verifies that MTM cells match verified IS/OOS measurements, that no
daily-close drawdown columns remain in the main table, and that expansion reveals
all unchanged daily diagnostics. It also checks downloads, reload, job-history
navigation and byte-identical saved paths across the existing v1/v2 policy flow.
The source and numerical evidence remain in [../v2](../v2/README.md); screenshots
here illustrate the current presentation without replacing earlier evidence.

The native synthetic reference has IS/OOS MTM drawdown **40.50 CU** for the two
one-contract candidates and **81.00 CU** for the two-contract candidates. Its
daily-close drawdown is **0.00 CU**, despite those intraday equity fluctuations.
`verification.json` records these expected observations and the unchanged daily
and path-file checksums. `monte-carlo-portal.png` shows the main table and closed
details; `daily-close-diagnostics.png` shows the expanded daily measurements.

```sh
ALPHAQUEST_MC_EVIDENCE_DIR=/tmp/alphaquest-mc-drawdown-ui .venv/bin/python -m pytest -q tests/test_campaign_monte_carlo_browser.py
```

The browser test server stops at teardown. Synthetic inputs and attestations do
not establish measured MultiCharts parity or readiness to trade.
