# Notebook-compatible prop analysis

Authority: `notebooks/PropFirm_MonteCarlo_Apex50K_2508.ipynb`, SHA-256
`f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b`.
Downloaded on 2026-10-26; 1,016,849 bytes, 23 cells; exact reviewed revision.
Executable cells take precedence over notebook prose. Stored outputs are not oracles.

Workflow: completed backtest report → configure prop analysis → source check →
run analysis → durable report with saved tables, charts and downloads.

The strict deterministic account engine, official-rule/instrument profiles,
bar-coverage inspection, export-session profiles and mandatory calendars are
retired. No current provider verification or trading authorization is implied.
Legacy `/api/prop-simulations` and `#backtests/prop/results/...` readers are retired;
old `data/prop_runs`, SQLite catalogues and `artifacts/prop-*` remain untouched.

Implementation increments: (1) native trade adapter, statistics, daily grid and
main evaluation; (2) evaluation/staged sizing and repeated attempts; (3) funded
first payout and size selection; (4) lifetime ladder, economics and robustness.
Each uses the same final portal workflow with immutable results.

## Adapter contract

Use saved `trades.csv`; entry UTC timestamps are converted to the saved source
IANA timezone and stripped of timezone for the notebook. Preserve original UTC,
direction, trade ID, quantities, strategy and dataset identities and costs.
Weekend trades are excluded before quantity normalization, followed by the OOS
filter. The grid spans filtered first/last weekdays, including zero-trade weekdays.
Constant quantities normalize profit to one mini equivalent; variable quantities
require explicit opt-in. No bar completeness or measured MAE is required.
Reference gross profit is pre-cost input. Saved per-side commission becomes round
trip commission. Slippage assumptions must reconcile observed fills, including
limit exits with no adverse slippage. Never deduct source costs twice.
Keep literal notebook defaults alongside source-derived overrides.

## Preserved model limitations

Holdout is reused for staged/funded/lifetime selection. Staged sizing omits DLL.
Daily evaluation omits DLL; trade/excursion evaluation ignore degradation kwargs.
Missing excursions fall back to close-only trade mode; partial MAE uses realized
loss (zero on winners). Raw excursions are not quantity-normalized by the notebook.
Weekdays, deadline fallback and 22-day inactivity are approximations. DLL
liquidation clips to the exact threshold. Executable funded drawdown is $2,000.
First-payout selection relaxes its ceiling when necessary; lifetime falls back
to safest size. Acquisition and repeated attempts use shortcut formulas.
Fractional mini/micro equivalents are analytical scaling, not actual micro fills.
