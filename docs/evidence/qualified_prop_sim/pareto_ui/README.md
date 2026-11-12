# Pareto chart readability — 12 November 2026

These are UI outputs from the **actual existing saved local report**
`5d5d999ba9a5479183fbe66cbeb04576`. No synthetic/mocked values, source rerun,
new simulation, replacement report or result store was used for these captures.
Earlier synthetic calculation evidence and Pareto snapshots remain unchanged.
The saved numerical report is historical research output, not a future forecast.

## Reproduce in the portal

1. Open `http://127.0.0.1:8000/#prop-sim?analysis=5d5d999ba9a5479183fbe66cbeb04576`
   and scroll to **Evaluation cost/time Pareto curve**. Do not launch another job.
2. The default **Frontier detail** fits the axes around the existing frontier,
   including nearby resolved sizes. This saved report has **53 resolved sizes**,
   **5 frontier configurations** and **7 unresolved/censored sizes**. At the
   captured desktop width, **27 of 53** sizes are in the focused viewport.
   Cropping changes only presentation; all configurations remain in the table.
3. Hover/focus/click a point or use **Inspect size**. Selecting **27 MNQ** shows
   **271.44 USD** acquisition cost and **42.21 calendar days**, with its table row
   highlighted. This is inspection, not selection of an Evaluation winner.
4. Click **All sizes** for full context. All **53 resolved sizes** appear. There
   are no overlapping permanent size labels, and green frontier markers are
   drawn above nearby grey points. Selecting an off-view size from the picker
   automatically switches to this view so the inspected point is visible.
5. Return to **Frontier detail** and reduce the viewport to 390 pixels wide.
   Expect a readable chart and stacked inspector with no horizontal page
   overflow. Nice tick intervals adapt to the available width; axes explicitly
   fit the selected view rather than being forced to start at zero.
6. Download **Pareto chart SVG ↓**. The file includes the current viewport,
   markers, axes, legend text and inspected metrics. Reopening or changing views
   uses the already saved results and makes no POST request.

## Saved evidence

- `frontier-desktop.png`: focused frontier, nearby sizes and 27-MNQ inspection.
- `all-sizes-desktop.png`: full overview, preserving the same inspected size.
- `frontier-mobile.png`: the normal 390-pixel mobile presentation.
- `frontier-detail.svg`: actual chart download through the portal.
- `verification.json`: source ID, counts, inspection, before/after report SHA256,
  browser errors and mutation-request inventory.

The before/after serialized report digest is identical:
`199ce273e67de11195d0b65a184bf19f3515b3cf34c478c87a41f44c91fcab95`.
The verification observed **zero mutation requests and zero browser errors**.
It used the existing user server and started no persistent or temporary server.

## Focused automated validation

```sh
.venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_evaluation_pareto_chart_tradeoffs_ties_and_unresolved_rows
```

This three-second presentation test uses an isolated temporary normal-product
server; fixture oracles remain in tests and are not part of the actual saved
product evidence above. It verifies:

- Known cost/time tradeoffs and exact ties, unchanged row highlighting, and
  lower-left axis orientation.
- Forty tightly spaced frontier configurations plus two distant dominated
  outliers: focused versus full viewport, no permanent size labels, and frontier
  markers drawn last so grey markers cannot conceal them.
- Selecting a particular overlapping size, inspecting exact values and switching
  to full context automatically for an off-view choice.
- One-point frontiers, no supplied frontier, all-unresolved results, keyboard
  access, SVG download and mobile layout without horizontal page overflow.

The browser fixture stops its temporary server after testing. Chart updates
reuse a small SVG and disconnect their ResizeObserver on route changes; no new
library, background polling, source loading or simulation is introduced.
