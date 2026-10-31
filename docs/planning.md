# Planning costs

[Docs](README.md) / [Architecture](architecture.md)

Optional cost planning for proposed tools/hosting. These dated figures are not
current checkout quotes or requirements for running the local portal.

Planning estimates, not confirmed quotes; original workbook/review missing.

| Setup | USD/month | Six months |
| --- | ---: | ---: |
| MultiCharts + Parallels | 104 | 624 |
| MultiCharts + VPS; no Parallels | 144 | 864 |
| MultiCharts + VPS + Parallels | 149 | 894 |
| Optional Databento increment | 199 | 1,194 |

Also budget prop fees, trading costs, history, data/API rights, Windows, tax/FX,
storage/compute and extra AI charges. Track engineering hours separately; count
shared costs once. Parallels is a monthly equivalent: payment/renewal terms may
differ, and cancellation does not recover sunk or committed fees.
Existing AI/Sheets capacity can have zero extra subscription cost only while
included capacity is enough; review time still costs effort. Local AlphaQuest
has no external engine licence fee, but development, compute and maintenance
remain costs. A covered MultiCharts licence can serve both validation and
execution; count it once. Historical purchases and live feeds are separate.

### Price and source provenance

| Source | Checked | Observation / next check |
| --- | --- | --- |
| [MultiCharts](https://www.multicharts.com/purchase/); USD 99/month estimate | 2026-10-31 | Page did not establish the selected .NET plan/term price; estimate unverified. Obtain checkout quote. |
| [PickMyTrade](https://pickmytrade.com/pricing/) | 2026-10-31 | USD 50 monthly per connected broker login. Check route/broker costs; do not add automatically to direct MultiCharts. |
| [Databento](https://databento.com/pricing/) | 2026-10-31 | Standard USD 199/month; one month L2/L3 history, extra history usage-priced. Check CME dataset, period and rights. |
| Parallels USD 5/month equivalent | Unchecked | Missing source. Obtain edition, term, payment/renewal/tax and Windows cost. |
| VPS USD 45/month | Unchecked | Provider/configuration missing. Quote Windows setup, region, supervision and recovery. |

Before spending, save dated quotes/terms and hashes with campaign notes. Date replacements,
keep old estimates and update totals. Public pages change; these are not archived
checkout quotes. This document authorizes no purchase.

## Market data access

Checked 31 October 2026. Prefer the existing prop/Rithmic/MultiCharts route when
it exposes the required L1/L2 data for less total cost. “Free” means **no extra
feed charge under the actual plan**, not a free prop account, platform, API or
second session. The user's intended plan is Lucid/Rithmic; its exact L2
subscription/inclusion is not confirmed here.

| Source | What it supports / limit |
| --- | --- |
| Lucid [setup](https://lucidtrading.com/lucid-setup-guide/), [supported platforms](https://support.lucidtrading.com/en/articles/11404614-lucid-trading-supported-platforms), [CME depth](https://lucidtrading.com/product/market-depth-cme-only/), [depth bundle](https://lucidtrading.com/product/market-depth-full-bundle/) | Rithmic/MultiCharts is supported and market-depth products exist. Included non-professional feed wording does not identify free L2; public product pages do not expose an applicable price/entitlement. Confirm the account subscription. |
| Apex [Rithmic add-ons](https://apextraderfunding.com/help-center/rithmic/rithmic-trading-tools-add-ons-orderbook-market-data-2nd-login-cme/) | Lists L2 as a paid add-on: prop Rithmic access is not universally free depth. |
| MultiCharts [Rithmic connection](https://www.multicharts.com/trading-software/index.php?title=Rithmic), [L1/L2 guidance](https://www.multicharts.com/trading-software/index.php?title=Level_1_vs_Level_2_Market_Data) | DOM/depth connection support; this connection does not supply expired contracts. Newer L2 simulated-trading features do not prove our installed build, strategy API or queue-aware historical fills. |
| Databento [MBO schema](https://databento.com/docs/schemas/mbo) | Individual order events/IDs (L3); our planned paid option when needed data is not exposed through the existing route. Check history, API and rights separately. |
| Rithmic [exchange coverage](https://www.rithmic.com/platforms/exchanges) | Also lists MBO for CME. This does not establish MBO entitlement or exposure through MultiCharts; Databento is a project choice, not the only possible L3 supplier. |

L2 aggregates depth by price; MBO/L3 identifies individual orders. Choose fields
and an accessible interface, not just a provider's level label. No live account,
API or installed-platform permission was tested by this document review.
