# Provider rule review — 8 November 2026

This is a dated review of primary documentation for the preserved 50K Apex EOD
and LucidFlex models. It does not change their numerical rules, certify an
account entitlement, or establish when a published rule first became effective.
Historical reports retain their original snapshots and assumptions.

New independent phase reports save `provider_rules.json` through the normal
AnalysisStore report and ZIP. Each field records the modeled value, a short
primary-document observation, its URL, the review date, and any unresolved gap.
`VERIFIED_DOCUMENT` means that the published wording was checked. `UNVERIFIED`
blocks a production-qualified verdict. A fixed modeled receipt date is not an
observed bank receipt.

| Area | Preserved model and current evidence | Qualification consequence |
| --- | --- | --- |
| Apex expiry | The kernel uses 21 sessions. Official access lasts 30 calendar days from purchase. | Different clocks; `UNVERIFIED`. |
| Apex inactivity | Two $50 days in 21 sessions. Official policy uses a rolling 30-calendar-day window. | Calendar boundaries remain a model gap. |
| Apex payout consistency | The kernel accepts exactly 50%. Current wording excludes a single day at 50% or above. | Equality boundary is unqualified. |
| Apex request amount | The model waits for the full sequential cap. Official rules allow requests from $500. | Full-cap requesting is a declared research policy. |
| Apex tiers | The model uses $6,000 for the final tier. The published adjacent ranges overlap at $5,999. | Exact boundary requires clarification. |
| Apex activation | The model activates automatically after a saved session delay. Official pass processing follows the close and allows seven calendar days to activate. | Operational approval and deadline behavior are unqualified. |
| Lucid standard consistency | The current evaluation overview and customization pages both specify 40%; 50% is a separate add-on. | Earlier reports' dated documentation-conflict note is preserved; it is no longer the current observation. |
| Lucid DLL | On/off and a soft session lockout are documented. The preserved enabled amount is $1,200. | Numeric amount and its above-floor behavior were not independently established in the reviewed page. |
| Settlement | Both providers describe approval/processing dependencies. The model uses an explicit fixed calendar lag and may settle a pending claim after termination. | Approval, denial, bank timing and post-termination entitlement remain unverified. |

Sources for those differences: [Apex evaluation access](https://apextraderfunding.com/help-center/billing/evaluation-plan-fees-and-access-explained/),
[Apex inactivity](https://apextraderfunding.com/help-center/billing/inactivity-policy-on-performance-accounts-pa/),
[Apex EOD payouts](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/),
[Apex tiers](https://apextraderfunding.com/help-center/additional-helpful-items/scaling-levels-pa-explained/),
[Apex activation](https://apextraderfunding.com/help-center/billing/pa-activation-process-deadline-explained/),
[Lucid evaluation](https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account),
[Lucid customization](https://support.lucidtrading.com/en/articles/16226050-lucidflex-customization),
[Lucid payout processing](https://support.lucidtrading.com/en/articles/12945796-lucidflex-payouts),
[Apex payment processing](https://apextraderfunding.com/help-center/additional-helpful-items/payout-method-information/).
The generic Apex processing page also contains eligibility wording inconsistent
with the EOD-specific page; it does not resolve EOD-specific approval-day rules.

Other reviewed fields include targets, EOD drawdown, contract limits, Lucid
scaling, payout shares/caps and inactivity. Sources are saved next to each field.
Purchase and activation prices are the saved user assumptions; no authenticated
checkout quote was obtained. Numerical agreement with local tests remains
separate from provider parity and live deployment readiness.

The executable review lives in `alphaquest/prop/rule_provenance.py`. Its source
hash is included in each independent phase implementation identity. Changing a
review or calculation cannot silently authorize an older frozen package. Missing,
unknown or altered captured reviews cannot certify deployment.
