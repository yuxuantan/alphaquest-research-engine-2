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

## Runtime and persistence

Numerical functions live in `alphaquest/prop/model.py` with explicit per-instance
state. `analysis.py` runs extracted cell calculations; `adapter.py` owns source
mapping and Decimal cost reconciliation. HTTP handlers orchestrate only.
NumPy 2.5.4 / pandas 3.1.0 are pinned. Reference execution in
`scripts/prop_notebook_reference.py` compiles original pinned notebook cells into
a fresh namespace, replaces upload with a temporary canonical CSV, injects explicit
settings, and omits presentation. It does not import production numerical code.
Bootstrap CI retains the notebook's fixed seed 42 and 10,000 draws; bounded
batches preserve flattened random draw order. Main/sweep counts are never reduced.

Native source presets retain saved per-side costs as round-trip overrides.
When limit fills differ from nominal slippage, the source preset explicitly
uses observed mean normalized slippage to reconcile aggregate baseline net;
per-trade differences remain visible in CSV. This is still the notebook's
constant per-trade formula, not a reconstructed execution model.

`data/prop_analyses` is the single new-format catalogue and result store. Jobs are
queued, running, complete or error. One worker bounds concurrent memory; each job
has its own model state. Duplicate active requests return the same job. Restarted
incomplete jobs become errors. Files publish by directory rename before catalogue
completion; downloads are available only for completed jobs. Source hash is
rechecked before publication. Reopening reads saved files without computation.
JSON/CSV/ZIP downloads contain source identities, exclusions, UTC/native dates,
input hash, resolved settings and origins, literal defaults, notebook/model/source
hashes, application commit, runtime and seed streams. No legacy results migrate.

Resource bounds reject oversized requests explicitly: 100,000 trades, 20,000
weekdays, 100,000 simulations per call, 64 sizes and 300 retained sample paths;
horizon guards are bounded separately. The server never silently truncates counts.

## Sizing and attempt sample semantics

Main simulation uses the full filtered sample. Cell 8 selects on the early
training weekday slice and evaluates the winner on validation with seed +2600;
its sweep uses PROP_MC_SIMS and common seed +2000. Cell 8b reuses validation and
seed +15000, omits DLL, rounds stage sizes to two decimals, and uses notebook
CI comparisons. Paths use seed +5000 and the current sample. Correlated attempts
use selected validation pass rate; independent attempts use the main pass rate.
The literal ATTEMPT_FEE=100, EVAL_FEE=100 and PA_ACTIVATION=140 remain available;
pricing presets explicitly override all three while leaving BLOWN_COST=150.

## Funded first payout

Cell 11's executable rules, including the $2,000 drawdown inherited from the
challenge, are saved with the report. Funded processing stays at trade resolution
with USE_MAE tied to the effective evaluation engine, even for daily evaluation.
Qualifying, strict consistency comparison, 22-trading-day inactivity and horizon
outcomes preserve original calculation order. Sweeps use seed +8000; detail at
the selected size uses +9000. Net EV subtracts (blown + inactive) × BLOWN_COST.
If no size meets MAX_BLOWN_RATE, the notebook's all-sizes fallback is retained and
marked. No official-provider profile or evidence approval is involved.
