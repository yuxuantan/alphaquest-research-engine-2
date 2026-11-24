# IS Narrow fine-grid plateau evidence

Labeled synthetic source and actual normal-portal outputs for `is-narrow-v3`.
These are arithmetic and workflow evidence, not a measured trading edge or
MultiCharts parity claim. All test servers stop during fixture teardown.

- `SYNTHETIC-source.csv`: uploaded through the normal dataset API.
- `narrow-results.json`: native results and complete plateau assessments for
  the two-contract Broad branch.
- `is-narrow-package.json`: downloaded confirmed choices, policy, local steps,
  neighbor results, and source/execution identities.
- `is-narrow-portal.png`: ordinary IS Narrow page showing the criteria and
  expanded plateau evidence.
- `journey.json`: generated workflow IDs and expected observations.

Recreate the journey in an isolated temporary app:

```sh
ALPHAQUEST_NARROW_EVIDENCE_DIR=/tmp/alphaquest-plateau-evidence \
  .venv/bin/python -m pytest -q \
  tests/test_campaign_narrow_browser.py::test_narrow_portal_two_broad_branches_columns_and_oos_handoff
```

For manual reproduction, start the ordinary app with an empty temporary data
directory (stop it with Ctrl-C afterwards):

```sh
ALPHAQUEST_DATA_DIR="$(mktemp -d /tmp/alphaquest-plateau.XXXXXX)" \
  .venv/bin/uvicorn alphaquest.app:app --host 127.0.0.1 --port 8012
```

1. Visit `http://127.0.0.1:8012/`. Upload the synthetic CSV as UTC, tick size
   0.25, point value 10, symbol SYNTHETIC.
2. Create a Consecutive Green Hold campaign workflow. Use IS 2024-01-01 through
   2025-12-31 and OOS 2026-01-01, initial capital 10,000, one tick of baseline
   slippage, and one CU commission per contract per side. Run mechanics and
   inspect the evidence before completing the labeled synthetic attestation.
3. In Broad, fix green-bar count 3 and hold minutes 20; vary contracts 1..2,
   step 1. Run and confirm both rows.
4. For each Broad branch, fix green-bar count 3 and the selected contracts;
   vary hold minutes 17..20, grid step 1, local plateau step 1. Run the grid.
5. Expect hold 18 and 19 to pass all seven checks, with 100% neighbor profit
   retention. Hold 17 and 20 have missing lower/higher local values and cannot
   be selected, even though their own results are profitable.
6. Confirm the two interior rows per branch and download the saved package.
   OOS navigation becomes ready after both branches are confirmed; this does
   not execute OOS.

Independent expected values: 120 source days × 78 CU net/day = 9,360 CU at one
contract. The saved extra-slippage rerun deducts 12 fills/day × 0.25 points ×
10 CU/point × 120 days = 3,600 CU more, leaving 5,760 CU. The two-contract
branch doubles both amounts. Identical hold-17..20 outcomes give 100% local
retention. These expectations are derived from the synthetic trade design,
not from the admission verdict.

`refinement/` records a second actual portal journey: explicitly refine Broad
hold 20 to Narrow values 18..21 with local step 1. Hold 19 passes. Hold 20 has
9,360 CU net but fails its plateau: neighboring hold 21 earns 1,800 CU, only
**19.23%** retained profit, and its extra-slippage net is **−1,200 CU**. The
boundary rows 18 and 21 lack one side. This proves that the gate rejects a
profitable interior setting when nearby behavior falls off sharply. Recreate
that separate journey with:

```sh
ALPHAQUEST_REFINEMENT_EVIDENCE_DIR=/tmp/alphaquest-plateau-refinement \
  .venv/bin/python -m pytest -q \
  tests/test_campaign_narrow_browser.py::test_narrow_portal_explicit_local_refinement_and_saved_result
```

The focused API tests also reject below-70% retention despite positive profit,
zero stressed profit, missing internal neighbor reports, invalid steps, and
stale previews. They verify that coarse older grids can be replaced without
changing their saved reports, while confirmed v1/v2 choices keep their policy.
