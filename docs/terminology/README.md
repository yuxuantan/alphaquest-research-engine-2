# AlphaQuest terminology

Use these terms when describing what AlphaQuest tests, how it tests it, and
where the result is saved.

## Core terms

| Preferred term | Meaning |
| --- | --- |
| **Strategy** | The trading rules implemented in code. A strategy defines how to decide when to enter, exit or manage a position. |
| **Strategy parameter** | A named input defined by the strategy, such as `hold_minutes`. A **parameter value** is one setting for that input, such as `20`. Use **strategy parameters** in prose and the existing `strategy_parameters` field where the API uses it. |
| **Strategy configuration** | One strategy with one complete set of parameter values. Changing a parameter value creates a different configuration of the same strategy. Use **configuration** as shorthand once the context is clear. |
| **Dataset** | The saved market data used by a backtest, with its instrument and timestamp settings. |
| **Research split** | The declared **in-sample (IS)** window for development and selection and the later **out-of-sample (OOS)** window for assessment. |
| **Execution settings** | Inputs to the backtest engine, such as starting capital, slippage and commission. |
| **Backtest** | A historical replay of one strategy configuration on a dataset over specified dates, using the chosen execution settings. Use **backtest run** for a particular execution and **backtest report** for its saved trades, metrics and input record. |
| **Parameter grid** | A declaration of the values to test for each parameter. Each generated combination gives one strategy configuration. Fixing every parameter at one value gives a one-configuration grid. |
| **Parameter search** | Evaluates the configurations in a grid. The portal action is **Run parameter search** for multiple configurations and **Run backtest** for one. The optimization API calls the grid job an **optimization**. |
| **Backtest batch** | The saved job that groups trials and tracks their progress. |
| **Trial** | One entry in a backtest batch for a specific configuration. A completed trial links to its backtest report. |
| **Validation study** | A saved research record for one strategy, dataset, and IS/OOS split in **Strategy Validation**. It groups the related backtests, grids, reviews and selections across **Mechanic validation → IS Broad → IS Narrow → OOS**. |
| **Tested configuration** | A configuration evaluated by a parameter search. Use **Select configurations** for the controls that choose which eligible configurations continue. |
| **Frozen selection** | A saved record of the exact confirmed configurations, their source reports and settings. **Confirm selection for OOS** saves the Narrow selection for later assessment. |
| **Qualified configuration** | A configuration that passed the validation checks required by Prop Desk. **Open IS backtest report** opens the selected configuration's exact IS source report. |

[Strategy parameters](../../alphaquest/strategies/registry.py) ·
[Backtest contract](../backtest_contract.md) ·
[Parameter grids](../optimization.md) ·
[Strategy Validation workflow](../workflow_screening.md)

## How they fit together

For **Consecutive Green Hold**, `green_bar_count`, `hold_minutes`, and
`contracts` are strategy parameters. Holding for 20 minutes after three green
bars at one contract is one **strategy configuration**.

1. A grid that tries 3 and 4 green bars while keeping the other two values fixed
   produces two **configurations** and two **trials**. The completed trials each
   have an IS **backtest report**.
2. Within a **validation study**, the grid might be part of **IS Broad**. The
   study also holds its mechanics review, Narrow grids, confirmed
   selections and OOS results.
3. If the three-bar configuration is confirmed after **IS Narrow**, running it
   on the later OOS dates produces a separate **backtest report** for the same
   **configuration**. Changing only slippage for a cost-stress replay also
   keeps the configuration and changes the backtest's execution settings.

[Consecutive Green Hold parameter definitions](../../alphaquest/strategies/consecutive_green_hold.py) ·
[Validation OOS rules](../workflow_screening.md#oos--implemented-policy-campaign-oos-v1)

## Use the specific name when it matters

- In **Strategy Validation**, choose a **strategy**, then open a saved
  **validation study** or choose **New validation study**. Each saved study shows
  its strategy, dataset, IS dates, and OOS dates.
- Use **Evaluation sizing study** and **Funded sizing study** for the account
  studies that compare sizes using saved IS backtests or trials. A sizing study
  can include configurations from several strategies.
- **Validation stage** means a step such as IS Broad. **Account phase** means
  Evaluation or Funded.
- **Compare configurations** when the parameter values differ. **Compare
  backtest reports** when the comparison is between saved runs, such as an IS
  run and its matching OOS run.

[Evaluation and Funded sizing studies](../research_campaign_api.md)
