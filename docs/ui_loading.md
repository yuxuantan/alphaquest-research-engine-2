# Loading feedback

The portal uses `alphaquest/web/loading.js` and shared CSS for loading feedback.
It is loaded before the feature scripts in `web/index.html`. It changes neither
requests nor financial calculations and needs no worker/server restart.

## Section loading

Use an existing status element for a subsection that fetches data independently:

```js
const finish = portalLoading.begin(status, {label: 'Loading saved results…'});
try {
  const response = await portalLoading.fetch(url);
  const result = await response.json();
  if (!response.ok) throw Error(result.detail);
  renderResults(result);
  status.textContent = 'Saved results loaded.';
} catch (error) {
  status.textContent = error.message; // Retain the normal retry/recovery action.
} finally {
  finish();
}
```

Status elements should retain their existing `role="status"`/live-region labels.
The helper adds a decorative CSS spinner and `aria-busy`, without disabling
controls, changing focus, hiding useful existing results or creating requests.
Each completion handle owns its state: an older response cannot clear a newer
indicator. The original busy attribute is restored when the current read ends. A temporary
label is restored if the caller leaves it unchanged, so refreshing unchanged
results cannot leave a stale Loading message.
Capture a completion handle for the actual element; do not look up a replacement
metric by ID when finishing an older request.

For initial content that will be replaced wholesale, use
`const finish = portalLoading.region(host, 'Loading…')` with the same `finally`
cleanup. Its temporary paragraph is a live status message. For a temporary
placeholder guaranteed to be replaced by either results or an error, use
`portalLoading.message('Loading…')`. Clear it explicitly if an error changes the
text in place instead of replacing the placeholder.

Sections include dataset/strategy libraries, campaign workflow and phase shells,
Job history, backtest choices/worker counts, research/source selectors, report
trades/timing/prop summaries, lazy diagnostics, Prop Sim source choices and phase
reports, and advanced task/observation/source pickers. These indicators describe
loading saved data. Backtest/simulation execution retains its own progress bars,
worker counts and cancellation actions.

## Request fallback

Feature scripts use `portalLoading.fetch` instead of calling `fetch` directly.
It returns the normal browser Response and preserves HTTP status, rejection and
abort behavior. Pending fetch responses may show the small header indicator
after 200 ms when no visible local loading message covers the work. Fast responses
avoid that indicator. Section owners keep their own indicators through response
body decoding and rendering. Completion of one request does not clear other
pending requests; requests started on a previous route do not hold the current
route's header indicator open. This adds no polling, calculations or endpoint.

The spinner is CSS-only, respects reduced motion with a static graphic plus text,
and never intercepts pointer or keyboard interaction. Mobile layouts retain the
same visible labels and allow normal navigation.

## Verification

Run only the affected browser checks:

```sh
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest -q \
  tests/test_portal_loading_browser.py \
  tests/test_prop_sim_browser.py::test_form_and_navigation_remain_usable_while_configurations_load \
  tests/test_prop_sim_browser.py::test_qualified_configuration_load_failure_has_retry_without_resetting_settings
```

The checks hold real product GET requests in the browser to inspect pending
states, then continue them to the temporary portal. Clearly labeled synthetic
read failures exercise recovery; they do not generate financial outcomes. A
normal uploaded arithmetic dataset/backtest/report verifies that timing evidence
can load independently of the usable core report. Checks cover success, failure,
retry, out-of-order completion, navigation, reduced motion and mobile overflow.
Temporary test servers stop during fixture teardown. Screenshots, JUnit results
and read-only live-portal verification are in `artifacts/portal-loading-20261121/`.
