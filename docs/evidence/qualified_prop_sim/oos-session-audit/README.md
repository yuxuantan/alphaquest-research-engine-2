# Frozen OOS session audit admission — 13 November 2026

This increment fixes saved-source OOS admission through the existing campaigns,
Prop Sim portal and AnalysisStore. It does not add a new page, API or result
store. Original reports, audit dictionaries, source files, frozen selections and
failed attempt history remain intact.

## Retry the existing saved simulation

1. Refresh `http://localhost:8000/#prop-sim?analysis=2d19909ce7b3404ca73adb534d6a8d2a`.
2. The existing frozen choices remain selected and compatible. Click **Run OOS
   assessment** in the desired phase. No new IS calculation or freeze is needed.
3. The request admits the frozen family despite different IS/OOS session audit
   statistics. Its effective source window is **2025-01-02 → 2026-07-07**: the
   original declared split remains **2025-01-01 → 2026-07-07**, and the first
   saved session follows the January 1 holiday. Missing dates are not invented.
4. Follow progress here or through Job history. The new assessment and its JSON
   and evidence ZIP remain downloadable. Prior failed attempts remain history;
   they are not rewritten or silently retried.

`actual-run-readonly-admission.json` verifies all four Evaluation choices and
all four Funded choices against the exact existing frozen packages. It also
checks that the original IS candidate identities are unchanged. This inspection
started no calculation and wrote no API/catalogue/source changes. Reproduce
against the same existing local workspace/server:

```sh
PYTHONPATH=. .venv/bin/python \
  docs/evidence/qualified_prop_sim/oos-session-audit/verify_actual_readonly.py
```

The script uses GET requests and SQLite `mode=ro`; its only output write is the
local inspection JSON beside the script. It does not create a server.

## Actual calendar-strategy calculation and rejection evidence

```sh
ALPHAQUEST_OOS_AUDIT_EVIDENCE_DIR=/private/tmp/oos-audit-reproduction \
  .venv/bin/python -m pytest -q tests/test_prop_oos_source_identity.py
```

The normal-product synthetic journey uses the real VWAP strategy and reviewed
NQ calendar: dataset upload -> declared IS backtest -> phase campaign/source
checking -> existing local phase worker -> immutable freeze -> ordinary OOS
backtest -> phase assessment -> saved JSON/ZIP exports. Both Evaluation and
Funded run in isolated temporary catalogues. No fixture results or measured
excursions are substituted into production calculations.

Independent expected trade arithmetic: a long fills at **115.25**, exits at
**130.00**, and pays **$2** total commission on one NQ. Thus
`(130.00 - 115.25) × $20 - $2 = $293` per source trade. The two IS sessions earn
**$586**, and three OOS sessions earn **$879**. The IS calendar audit contains
**2 sessions including one early close**; OOS contains **3 regular sessions**.
The generated example dates/plan hashes differ, while static strategy/calendar
rules and parameters match. The daily-reset input is explicitly 07:00 for this
morning-only synthetic source. The source split declares January 17 as OOS
start; its first saved OOS session is January 18, exercising the missing-first-
date boundary without changing that split.

For each phase, `evaluation/` or `funded/` retains the actual `is-report.json`,
unchanged `frozen-package.json`, `oos-report.json` and normal sealed
`oos-evidence.zip`. The OOS request uses the saved coverage, keeps the selected
20-MNQ configuration, and produces an assessment-only report with no winner or
reselection. Existing IS/freeze bytes remain unchanged.

The same cases reject changes to parent, strategy parameters, strategy source
hash, dataset, execution commission, split, calendar snapshot, close buffer or
lookahead rule. The unit cases also cover unknown static fields, nonmutating
comparison, empty OOS coverage and exact directed implementation compatibility.
Fixture oracles remain in tests.

## Qualified Prop Sim portal regression

```sh
ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR=/private/tmp/oos-audit-product \
  .venv/bin/python -m pytest -q \
  tests/test_prop_sim_browser.py::test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey \
  tests/test_campaign_assessments.py::test_frozen_manual_oos_no_reselection_and_durable_history
```

This uses the existing labeled synthetic qualified campaign -> Prop Sim source
check -> Evaluation/Funded calculations -> freeze -> six OOS/diagnostic jobs ->
reload/download flow. `product/verification.json`, screenshots and the two OOS
ZIPs retain its saved output. The existing manual-OOS cases verify immutable
history and reject an unreviewed changed numerical implementation. Temporary
servers stop on teardown; the user's existing port-8000 server is left running.

## Source identity and historical compatibility

The admission file's source fingerprint changes from
`5fae2e873d053ed8315225cc8f72a2ca2926a73974e784941f4637dc1ba76e0a` to
`a078590de6c3f748e92b54775d900f8b7b9c5ec2ed4ab14b0e65ac94cfc3a051`.
`phase_dispatch.implementations_compatible` accepts this exact directed pair only
when every other source, kernel and environment identity is equal. It does not
remove changed files from fingerprints, rewrite old hashes, or accept unknown
future code. New assessment reports retain the actual current fingerprint and
the original frozen package. Changing any numerical source or calendar rules
still rejects. This narrowly reviewed admission compatibility keeps existing IS
reports usable without weakening calculation identity or rerunning selection.
