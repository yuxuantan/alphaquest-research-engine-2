"""Inspect compact optimization through reports, detailed replay and native prop analysis."""

from datetime import datetime, timedelta
from decimal import Decimal
import gzip
from hashlib import sha256
import json

from test_backtests_browser import browser, page, portal, playwright
from research_fixtures import reserved_source,declare_in_form


def test_compact_storage_and_normal_report_to_prop_workflow(page, portal, tmp_path):
    # Two weekday sessions, each with exactly one trade: enter at 100.25,
    # exit at 101.75, point value 10, commissions 2 -> net 13 CU per contract.
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for day in (5, 6):
        for minute in range(1440):
            stamp = datetime(2026, 1, day) + timedelta(minutes=minute)
            prices = "99,100,99,100" if minute < 3 else "102,102,102,102"
            lines.append(stamp.strftime("%m/%d/%Y,%H:%M") + f",{prices},100,60,40")
    source = tmp_path / "SYNTHETIC-compact-report.csv"
    raw,split=reserved_source(("\n".join(lines)+"\n").encode())
    source.write_bytes(raw)
    page.goto(portal["url"])
    page.locator("#csv-file").set_input_files(source)
    page.locator("#dataset-name").fill("SYNTHETIC compact optimization review")
    page.locator("#dataset-tick-size").fill("0.25")
    page.locator("#dataset-point-value").fill("10")
    page.locator("#validate-button").click()
    playwright.expect(page.locator("#validation-result")).to_contain_text("Validation passed")
    page.locator("#save-button").click()
    playwright.expect(page.locator("#validation-result")).to_contain_text("Dataset saved")
    dataset = next(d for d in page.request.get(portal["url"] + "/api/datasets").json()
                   if d["name"] == "SYNTHETIC compact optimization review")
    page.get_by_role("link", name="Strategies", exact=True).click()
    page.get_by_role("link", name="New backtest →", exact=True).click()
    page.locator("#backtest-mode").select_option("exhaustive")
    playwright.expect(page.locator("#optimization-ranges tr")).to_have_count(3)
    page.locator("#backtest-dataset").select_option(dataset["id"])
    declare_in_form(page,split)
    page.locator("#backtest-slippage-ticks").fill("1")
    page.locator("#backtest-commission").fill("1")
    settings = page.request.get(portal["url"] + "/api/optimizations/settings").json()
    page.locator("#optimization-workers").select_option(str(min(2, settings["max_workers"])))
    page.get_by_label("Contracts end", exact=True).fill("2")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=30000)
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(2)
    optimization_url = page.url
    job_id = page.url.rsplit("/", 1)[1]
    rows = page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results").json()["items"]
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in rows] == [26, 52]
    compact = page.request.get(f"{portal['url']}/api/backtests/{rows[0]['run_id']}").json()
    assert compact["report_storage"]["detail"] == "compact"
    root = portal["app"].state.runs.root
    folder = root / compact["id"]
    before = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    baseline_response = page.request.post(portal["url"] + "/api/backtests", data={
        "report_detail":"full",
        "sample_split":split,
        "dataset_id": dataset["id"], "strategy_id": compact["run_metadata"]["strategy"]["id"],
        "strategy_parameters": compact["run_metadata"]["strategy"]["parameters"],
        "execution_settings": compact["execution_settings"],
    })
    assert baseline_response.status == 201, baseline_response.text()
    baseline = baseline_response.json()
    assert baseline["summary"] == compact["summary"]
    for name in ("trades.csv", "equity.csv"):
        assert (root / baseline["id"] / name).read_bytes() == (folder / name).read_bytes()
    sizes = lambda path: {p.name: p.stat().st_size for p in path.iterdir()}
    compact_sizes, baseline_sizes = sizes(folder), sizes(root / baseline["id"])
    # The new comparison deliberately retains every bar in a separate aligned
    # CSV for both report modes. Preserve the original native-report compaction
    # gate, and account for this additional feature's storage explicitly.
    comparison_names = {'market_benchmark.json', 'market_equity.csv'}
    native_size = lambda values: sum(size for name, size in values.items() if name not in comparison_names)
    assert native_size(compact_sizes) < native_size(baseline_sizes) / 50
    assert (folder / 'market_equity.csv').read_bytes() == (root / baseline['id'] / 'market_equity.csv').read_bytes()
    page.locator('#optimization-results tbody td[data-column="run_id"] a').first.click()
    playwright.expect(page.locator("#report-storage-note")).to_contain_text("Compact report")
    playwright.expect(page.locator("#equity-chart")).to_be_visible()
    playwright.expect(page.locator("#report-summary")).to_contain_text("26.00")
    compact_url = page.url
    page.screenshot(path=str(tmp_path / "compact-backtest.png"), full_page=True)
    with page.expect_download() as downloaded:
        page.locator("#report-json-download").click()
    downloaded.value.save_as(tmp_path / "compact-report.json")
    assert "equity" not in json.loads((tmp_path / "compact-report.json").read_text())
    page.locator("#report-generate-detail").click()
    playwright.expect(page).not_to_have_url(compact_url, timeout=30000)
    playwright.expect(page.locator("#report-storage-note")).to_contain_text("compressed with gzip")
    detailed_id = page.url.rsplit("/", 1)[1]
    detailed = page.request.get(f"{portal['url']}/api/backtests/{detailed_id}").json()
    assert detailed["summary"] == compact["summary"]
    with page.expect_download() as downloaded:
        page.locator("#report-json-download").click()
    downloaded.value.save_as(tmp_path / "full-report.json.gz")
    expanded = json.loads(gzip.decompress((tmp_path / "full-report.json.gz").read_bytes()))
    assert len(expanded["equity"]) == 2881 and len(expanded["trades"]) == 2
    assert expanded["equity"] == json.loads((root / baseline["id"] / "report.json").read_text())["equity"]
    assert (tmp_path / "full-report.json.gz").stat().st_size < baseline_sizes["report.json"] / 10
    page.goto(compact_url)
    page.locator("#report-prop-setup").click()
    playwright.expect(page.locator("#prop-config")).to_be_visible()
    # Reject an unsupported configuration in the real flow before a valid check.
    page.locator("#prop-overrides").fill('{"unsupported_storage_test":1}')
    page.locator("#prop-check").click()
    playwright.expect(page.locator("#prop-status")).to_contain_text("Unknown prop analysis setting")
    playwright.expect(page.locator("#prop-run")).to_be_disabled()
    page.locator("#prop-overrides").fill("{}")
    page.locator("#prop-check").click()
    playwright.expect(page.locator("#prop-check-output")).to_contain_text("Source check passed")
    playwright.expect(page.locator("#prop-check-output")).to_contain_text("26.00")
    playwright.expect(page.locator("#prop-run")).to_be_enabled()
    page.screenshot(path=str(tmp_path / "prop-source-check.png"), full_page=True)
    page.locator("#prop-run").click()
    playwright.expect(page.locator("#prop-report")).to_be_visible(timeout=60000)
    playwright.expect(page.get_by_role("heading", name="Funded outcomes are unavailable")).to_be_visible()
    prop_url = page.url
    with page.expect_download() as downloaded:
        page.get_by_role("link", name="Report data (JSON)", exact=True).click()
    downloaded.value.save_as(tmp_path / "prop-report.json")
    prop = json.loads((tmp_path / "prop-report.json").read_text())
    assert prop["source"]["backtest"]["id"] == compact["id"]
    assert prop["source"]["reconciliation"]["source_totals"]["net_pnl"] == "26.00"
    assert prop["source"]["excursion_input"]["measured_mae_count"] == 0
    assert prop["calculations"]["evaluation"]["pass_rate"] == 0
    assert prop["calculations"]["funded"] is None
    page.screenshot(path=str(tmp_path / "prop-durable-results.png"), full_page=True)
    page.reload()
    playwright.expect(page.locator("#prop-report")).to_be_visible()
    page.locator("#prop-back").click()
    page.locator("#report-prop-setup").click()
    page.locator("#prop-saved a").first.click()
    playwright.expect(page).to_have_url(prop_url)
    playwright.expect(page.locator("#prop-report")).to_be_visible()
    assert {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()} == before
    (tmp_path / "verification.json").write_text(json.dumps({
        "synthetic": True, "source_bars": 2880, "optimization_id": job_id,
        "compact_run_id": compact["id"], "baseline_run_id": baseline["id"], "detailed_run_id": detailed_id,
        "expected_net_pnl": [26, 52], "actual_rows": rows,
        "compact_file_bytes": compact_sizes, "baseline_file_bytes": baseline_sizes,
        "detailed_file_bytes": sizes(root / detailed_id),
        "compact_reduction_percent": 100 * (1 - sum(compact_sizes.values()) / sum(baseline_sizes.values())),
        "native_compact_reduction_percent": 100 * (1 - native_size(compact_sizes) / native_size(baseline_sizes)),
        "additional_comparison_bytes": {name: compact_sizes[name] for name in comparison_names},
        "compact_report_sha256_unchanged": before, "prop_url": prop_url,
        "expected_prop_source_net_pnl": "26.00", "expected_measured_mae_count": 0,
        "expected_validation_pass_rate": 0, "funded_results_expected_unavailable": True,
        "normal_report_chart_and_downloads_verified": True, "prop_check_run_reload_reopen_verified": True,
        "unsupported_prop_setting_rejected": True, "optimization_url": optimization_url,
    }, indent=2) + "\n")
