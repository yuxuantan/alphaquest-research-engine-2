# Portal responsiveness — 2026-11-14 diagnosis and solution

The immediate outage is blocked terminal output on the web process's main
thread. The active analysis is still making progress. The stable launcher below
addresses this failure mode; the broader load protections are planned separately.

## Observed live state

The existing port-8000 service is Uvicorn with `--reload`: supervisor PID 70649,
web child PID 92680 at the time of inspection. Both stdout and stderr point to
`/dev/ttys002`. A three-second macOS stack sample places the main thread in
`TextIOWrapper.write → Buffered.flush → FileIO.write → write` for all 2,602 samples.
This blocks the event loop, including unrelated static HTML requests. It is
terminal logging/output backpressure; the native stack alone does not identify
the exact Python logging call or whether the terminal reader is paused.

The `/api/prop-sim` request timed out after 15 seconds with zero bytes; `/`
timed out after eight seconds with zero bytes. A non-destructive output-resume
request, equivalent to Ctrl+Q, did not restore responses. No log output was
discarded and no user process was stopped or restarted.

Active analysis `609ec63f9b2f4af2ad84c40d920eb484` is the Funded OOS historical
confidence job for simulation `ede834c9fea44f2fa663e481dd8d4582`. Its second
candidate is 14 MNQ with 10,000 historical refits. Four workers were active;
progress advanced from 2,074 to 3,745 of 10,000 during diagnosis. At 09:39:40
Singapore time, overall progress was 13,745 of 20,000 across the two sizes, with
approximately 19 minutes remaining for the current size according to saved ETA.
These are a time-stamped observation and estimate, not current/final status.
No active optimization was found in the backtest catalogue.

## Implemented mitigation, awaiting live switchover

`sh scripts/serve_portal.sh` now supplies the stable local startup path:

- One web process, with development auto-reload disabled, including an inherited
  `UVICORN_RELOAD` setting. Code edits cannot restart long analyses through the
  launcher. Existing numerical workers and their budgets remain unchanged.
- No per-request access logs. Structured server logs go to rotating files
  (`portal_logs/server.log`, 5 MiB plus three backups). Interpreter output and
  unexpected prints go to `portal_logs/process-output.log`, an append-only
  fallback rather than the terminal. This removes terminal output from serving.
- Bind the localhost port before application initialization and pass that socket
  to Uvicorn. Duplicate launches fail before recovery can mutate job statuses.
- Hold one process lock per data directory, so another stable launcher cannot
  create a second recovery owner on a different port.
- Read-only checks reject existing active prop, optimization or mechanic jobs
  unless `--recover-interrupted` is explicitly supplied for intended recovery
  after the previous server has stopped. A failed duplicate launch does not
  relabel live jobs interrupted.

Default logs are under `data/portal_logs`; `ALPHAQUEST_DATA_DIR` chooses another
library. The normal foreground stop is Ctrl+C. This launcher is for local macOS/
POSIX use and preserves the existing application/store/worker architecture.
It is not an additional scheduler, service or result store.

At the initial diagnosis the user-managed server was **not** switched or
restarted. The live recovery recorded below subsequently applied the new launcher
after the confidence job completed. A restart during confidence calculation would
lose unsealed in-memory refits and require recovery/recomputation; it is not a
zero-loss hot fix. Do not start another instance against the same live data to
work around an unresponsive page.

## Verification and limits

The automated check fills an output pipe with 65,536 bytes and leaves it unread.
The ordinary Uvicorn launch stalls. The stable launcher starts the actual
AlphaQuest application using a temporary empty library, serves `/`, Prop Sim
history/defaults/candidates and Job history, and opens the real `#prop-sim` form
in Chrome. The account selector remains interactive. It also checks occupied-port,
duplicate-data-owner and active-job rejection without modifying the guarded job.

The final measurements, screenshot and log files are in
[saved validation evidence](../artifacts/portal-responsiveness-20261114/validation.json).
The test was run while the user's existing four-worker confidence calculation
continued. The temporary test library did not run a calculation or contain the
user's full report history. This proves terminal-output isolation and basic
portal usability under concurrent machine load; it does not certify latency for
large report rendering or every task type. All owned temporary servers stopped.

Reproduce from the repository root:

```sh
.venv/bin/python artifacts/portal-responsiveness-20261114/verify_launcher.txt
```

The check uses the installed Chrome channel through Playwright and isolated
temporary data; it never restarts port 8000. Its verifier is saved as `.txt` to
avoid triggering the existing development server's Python-file watcher.

## Remaining solution for general task isolation

The following changes are proposed, **not implemented by this launcher**:

1. Route all web logging through a bounded non-blocking queue with a dedicated
   sink thread. Terminal isolation fixes the observed issue, but synchronous file
   logging can still wait on slow storage. Never fall back to synchronous stderr
   on a full logging queue. Keep dropped-log accounting and error visibility.
2. Render the Prop Sim page shell, history and selected job status independently
   of the source picker. Today `Promise.all(candidates, defaults, history)` gates
   the entire screen on a complete source-evidence audit. Load the picker
   separately, with its own retry/error state, while browsing saved results and
   navigation remain available. Recheck authoritative admission at Check/Run.
3. Keep status/progress reads strictly metadata-only. Cache presentation summaries
   of verified sealed reports by immutable report identity, with bounded memory
   and proper invalidation. Current `fingerprint()` rereads reports, ZIPs and all
   captured files; summary routes also parse full reports before pruning fields.
   Do not weaken source/seal verification at launch/reuse or create a new store.
4. Keep CPU-heavy calculations in the existing bounded process runtime; keep
   event-loop work small and reserve capacity for interactive requests. Bound
   concurrent expensive reads, minimize lock duration around publication, and
   retain the shared admission/reuse/cancellation transaction guarantees. Do not
   add multiple Uvicorn application owners: startup owns job recovery.
5. Add explicit request deadlines, navigation cancellation, single-flight polling
   and backoff to the frontend. Preserve the last visible state when a refresh
   fails; a late response must not overwrite another page. Surface a stalled
   request clearly while allowing navigation and local form interaction.

Acceptance should exercise actual Prop Sim/Job history journeys during IS search,
four-worker OOS confidence, source checks and large report publication/downloads.
Suggested local targets: interactive metadata responses p95 below 500 ms and page
shell visible within one second on the reference machine; test thresholds must
allow meaningful CI variation. Also inject blocked output, slow report reads,
full logging queues and slow/disconnected clients. Preserve exact numerical
outputs, seeds, path counts, frozen selection, stop intent and old sealed reports.
These targets are engineering proposals, not measured guarantees for all loads.

Relevant primary documentation:
[Uvicorn settings](https://uvicorn.dev/settings/) and
[Python logging handlers](https://docs.python.org/3.12/library/logging.handlers.html#queuehandler).

## Live recovery after the terminal/VS Code restart — 2026-11-14

At 09:57 Singapore time the same supervisor/web processes still owned port 8000
and stdout/stderr still targeted `/dev/ttys002`. A second sample again placed all
1,683 main-thread samples in the terminal write call. The listening socket kept
the address reachable while HTTP requests received no response. The editor
restart leaving terminal output undrained is consistent with this evidence; the
cause of the editor's own failure was not established.

The remaining Funded job then completed, both automatic phase stages became
`complete`, and no prop, optimization or mechanic jobs remained active. Before
recovery, all four IS/OOS report/ZIP seals were verified. Only the exact old idle
portal tree was terminated; the blocked supervisor/web child required force after
a termination grace period. The stable launcher started on the same data and port
at 09:58:51, PID 25985, detached from the VS Code terminal and with file output.
All four reports/ZIPs retained their seals after startup; no calculations reran.

Live HTML and history requests returned HTTP 200 in approximately four
milliseconds in the first check. Real-data source admission listing took about
0.86 seconds in a subsequent measurement; this is separate from the terminal
outage and supports the planned independent picker loading. The actual Prop Sim
browser form and measurements are captured in
[live restored validation](../artifacts/portal-responsiveness-20261114/live-restored-validation.json),
[recovery record](../artifacts/portal-responsiveness-20261114/live-recovery.json), and
[restored portal screenshot](../artifacts/portal-responsiveness-20261114/live-restored-prop-sim.png).

This replacement server is intentionally persistent. Stop this particular
instance with `kill -TERM 25985` when no analysis needs to finish. For future
starts, run `sh scripts/serve_portal.sh`; avoid the old `--reload` invocation for
long analysis sessions.
