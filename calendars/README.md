# NQ futures closure calendar

[`cme_nq_closures.csv`](cme_nq_closures.csv) records CME Globex **NQ futures**
holiday exceptions for **2016-01-01 through 2026-11-02**: the last ten complete
calendar years plus a current-year supplement for the existing dataset. It
contains **124 dates: 96 early closes and 28 full session closures**. The first
2016–2025 snapshot (116 dates) is preserved in Git commit `107c533`. Times are actual scheduled matching-stop times,
not strategy order cutoffs, cash-equity hours, settlement times or broker
margin deadlines. The five-minute strategy buffer is deliberately not stored.

The [AQ Python strategy](../docs/strategies/vwap_pullback_risk_sizing.md) now
loads this file once per run when EOD flattening is enabled. Its scheduled
cutoffs replace the earlier last-observed-bar inference. Existing saved reports
retain their original calculations and execution-model labels. The matching
C# strategy and its installation/qualification steps are in
[`multicharts/README.md`](../multicharts/README.md).

## Scope and date meaning

Use the **local session-ending date** in `America/Chicago`, including daylight
saving time. This is **not the official CME clearing trade date**. For example,
the holiday daytime portion of Monday 2024-09-02 stops at 12:00 CT even though
CME assigns the activity to the September 3 clearing trade date.

For the normal overnight convention, bars at/after 17:00 CT belong to the
following local session-ending date. Both strategy consumers also apply the
normal weekly trading schedule; weekends are not rows in this exception file.

- `early_close`: the session has trading before `close_time_local`; its
  remaining daytime portion is closed/halted. It may reopen at 17:00 CT for
  the **next** session, subject to that next session's calendar entry.
- `full_close`: there is no trading session ending on that date, including its
  preceding evening. `close_time_local` is empty. It does **not** mean the
  entire midnight-to-midnight civil date is closed: a holiday's 17:00 reopening
  belongs to the following date. For example, Christmas 2024 is closed, but
  December 25 at 17:00 starts the December 26 session.
- No exception row **within reviewed coverage** means use the regular session
  schedule. Absence outside reviewed coverage means **unknown**, not regular.
  Use the explicit `coverage_start` and `coverage_end` fields; the first/last
  exception dates do not themselves declare coverage.

The scope is scheduled holiday closures and the two national days of mourning.
It excludes routine maintenance, normal weekends, contract expiration cutoffs,
price-limit/circuit-breaker halts, unannounced outages and missing feed data.
For example, the scheduled 2025-11-28 close is represented; its technical outage
is not modelled as an advance holiday exception. This is not an exhaustive
historical market-status feed. Do not generalize this NQ file to other asset
classes or assume it certifies another contract's hours. MNQ did not exist
throughout this entire period.

## CSV columns

UTF-8, comma-separated, one header row, sorted by unique `session_date`.
Ordinary RFC 4180 quoting is allowed; consumers should use a CSV parser.

| Column | Meaning |
| --- | --- |
| `coverage_start` / `coverage_end` | Reviewed inclusive bounds; identical on every row |
| `session_date` | Session-ending local date, exactly `YYYY-MM-DD` |
| `closure_type` | `early_close` or `full_close` |
| `close_time_local` | Scheduled close/halt, 24-hour `HH:MM`; empty for `full_close` |
| `timezone` | `America/Chicago`, not fixed UTC-6 |
| `event` | Human-readable holiday/event |
| `source_url` | Dated notice or exchange schedule supporting this row |
| `source_note` | Where to look and any source discrepancy |
| `verified_on` | Date the historical fact was reviewed, **not** its announcement date |

## Sources and verification limits

Rows were reviewed against CME announcements and dated CME Globex schedules
republished by AMP Futures, Cannon Trading, Paragon Global Markets and DTN
IQFeed. Each row has its specific source; when the article has a table image,
read the **Equity/Equities Globex** row in that image. Some older CME direct
URLs no longer resolve, so dated broker/data-provider notices are retained as
sources. This is a manually reviewed historical transcription, not a
CME-certified calendar. Source URLs can subsequently change.

Start future maintenance from [CME Group Holiday and Trading Hours](https://www.cmegroup.com/trading-hours.html).
Select the date and NQ futures product. Use the **Globex** section, not Trading
Floor, ClearPort, NYSE/Nasdaq cash shares, or a settlement/clearing advisory.
An advisory's list of holiday dates alone does not establish futures hours.

Important independently checked cases:

| Date(s) | Scheduled outcome | Source observation |
| --- | --- | --- |
| 2021-01-18; 2021-09-06; 2024-01-15; 2024-09-02 | Early close 12:00 CT | The four AQ/MC discrepancy dates; five-minute buffer gives 11:55 |
| 2016-11-24 / 2016-11-25 | 12:00 / 12:15 CT | Thanksgiving Thursday and Friday differ |
| 2024-07-03 / 2024-07-04 | 12:15 / 12:00 CT | Pre-holiday and holiday differ |
| 2021-04-02; 2023-04-07; 2026-04-03 | Early close 08:15 CT | Good Friday overnight session remains tradable until 08:15 |
| 2016-03-25; 2017-04-14; 2018-03-30; 2019-04-19; 2020-04-10; 2022-04-15; 2024-03-29; 2025-04-18 | Full close | Do not impose the 08:15 exception on every Good Friday |
| 2018-12-05; 2025-01-09 | Early close 08:30 CT | CME mourning announcements; not full futures closures |
| 2019-09-02 | Early close 12:00 CT | AMP prose incorrectly says September 3; attached CME table correctly identifies Monday September 2 |
| 2021-12-24 | Full close | Observed Christmas; December 23 is regular |
| 2021-12-31 | Regular; no row | CME did not move Saturday New Year's Day to the preceding Friday |
| 2022-06-20 | Early close 12:00 CT | Juneteenth observance starts in this file in 2022; do not backfill earlier years |

The mourning announcements were published before the events:
[Bush, 2018-12-02](https://www.cmegroup.com/media-room/press-releases/2018/12/02/cme_group_u_s_equityinterestratemarketstoclosefornationaldayofmo.html)
and [Carter, 2024-12-30](https://investor.cmegroup.com/news-releases/news-release-details/cme-group-announces-trading-hours-us-national-day-mourning-honor).
Calendar lookup can avoid future-price lookahead, but `verified_on=2026-11-02`
does not prove when every source/version first became available. For a strict
point-in-time claim, retain the original notice and its publication time before
the simulated decision. An editable page's displayed publication date alone
does not prove the age of its current contents; several AMP pages are reused
for later years. No dates in this file were inferred from AQ price bars.

## Maintain it yourself

1. **Review a complete year**, including New Year, MLK, Presidents Day, Good
   Friday, Memorial Day, Juneteenth, Independence Day and the preceding day,
   Labor Day, both Thanksgiving days, Christmas Eve and observed Christmas.
   Check special announcements such as national mourning. Include only actual
   exceptions for NQ; do not automatically generate closure times from holiday
   names or copy the prior year's dates.
2. For each exception, open CME's NQ schedule and confirm when order matching
   stops, whether an overnight session exists, and when it reopens. Save the
   dated notice/PDF if available. Recheck before each upcoming holiday: CME says
   schedules can change and are usually finalized about two weeks beforehand.
3. Edit the CSV in a text editor, or import it into Excel with the date/time
   columns set to **Text**. Keep the header and ten columns. Add one row per
   session-ending date; set the actual close time for `early_close`, and leave
   it empty for `full_close`. Add the specific source URL, a short note and the
   date you verified it. Sort ascending and save as UTF-8 CSV. Do not save
   `12:00 AM`, change dates to locale formats, or subtract the strategy buffer.
4. Update `coverage_start`/`coverage_end` consistently in **every CSV row**,
   and the reviewed coverage in this document, **after** checking the entire
   added interval, including dates with no exceptions. Run the validator from
   the repository root with explicit new bounds. For an extension through 2026:

   ```sh
   .venv/bin/python scripts/validate_market_calendar.py \
     --start-date 2016-01-01 --end-date 2026-12-31
   ```

   This command does not fetch/generate holidays or establish their completeness.
   It checks format, ordering, duplicates, closure/time consistency, timezone,
   source fields and date bounds. A green result does not certify the notices.
5. Review `git diff -- calendars/`, then commit the reviewed update. Preserve the
   old CSV or Git commit with each backtest. New AQ runs record the CSV
   checksum and coverage; do not rewrite historical reports.
6. Copy the same reviewed bytes into Windows for MC .NET. Check that these match:

   ```sh
   shasum -a 256 calendars/cme_nq_closures.csv
   ```

   ```powershell
   Get-FileHash 'C:\AlphaQuest\calendars\cme_nq_closures.csv' -Algorithm SHA256
   ```

   File location can differ; contents must match. After connecting the strategy,
   reload/recalculate deliberately after an update rather than changing the
   calendar halfway through a backtest. Use your original report, prop
   configuration, source check, run and saved-report workflow to inspect new
   calculations; this file is not an OHLC dataset to upload through Datasets.

## Validate the delivered file

```sh
.venv/bin/python scripts/validate_market_calendar.py
```

Expected: `valid_structure`, 124 rows, 96 `early_close`, 28 `full_close`, and no
missing exception years. The output includes the file's SHA-256. To save a new
inspectable validation result (the command refuses to overwrite an old file):

```sh
.venv/bin/python scripts/validate_market_calendar.py \
  --output artifacts/cme-calendar-review-NEW/validation.json
```

For manual confirmation, filter `session_date` to the four discrepancy dates;
all must say `early_close,12:00,America/Chicago`. Filter to `2021-12-24`; the
time must be empty and the type `full_close`. There must be no `2021-12-31`
exception. Open the source URL on each sampled row and check its equity hours.
An attempted `full_close` row with `12:00`, a duplicate date, an invalid time,
or a timezone such as `CST` must fail structural validation.
