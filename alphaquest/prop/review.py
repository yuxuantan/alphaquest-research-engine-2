"""Small, saved demonstrations of configuration and adaptation, without an account engine.

Expected numbers are hand-calculated fixture oracles, never copied from adapter
output. Sources are synthetic and stored separately from the user's run library.
"""

import csv
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo, TZPATH

from ..backtest_runs import RunStore
from ..execution import execute
from ..reporting import generate_report, json_value
from ..strategy import Bar, CloseIntent, EntryIntent, ExecutionConfig
from .calendar import CalendarDay, DataWindow, SessionCalendar
from .rules import ResolvedProfile, get_profile, resolve_profile, resolve_simulation
from .sessions import InputError, InstrumentDeclaration, prepare_backtest
from .types import SimulationConfig, UserFees


D = Decimal
SPECIFICATION = Path(__file__).resolve().parents[2] / "docs" / "prop_simulation.md"
NOTEBOOK_SHA256 = "f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b"
EXPORTS = {"review.json", "checks.csv", "sessions.csv", "observations.csv", "profile.json",
           "simulation.json", "source.json", "calendar.json", "specification.md", "bundle.zip"}
DECLARATION = InstrumentDeclaration(
    "SYNTHETIC", "USD", D(".25"), D("10"), D("1"),
    "https://example.com/explicit-synthetic-rule-unit",
    "Synthetic fixture: USD 10 per point, .25 tick, one synthetic contract per rule unit. Not a real instrument mapping.",
)
SETTINGS = ExecutionConfig(D("10000"), D(".25"), D("10"), 1, D("1"))


class DemonstrationStrategy:
    """Predetermined synthetic intents; not a strategy available for real backtests."""

    def __init__(self, entries, closes):
        self.entries, self.closes = entries, closes

    def on_bar(self, bar, position):
        if bar.bar_number in self.entries:
            return EntryIntent(self.entries[bar.bar_number], "synthetic_entry")
        if bar.bar_number in self.closes:
            return CloseIntent("synthetic_exit")
        return None

    def on_finish(self, last_bar, position):
        return None


def wire(value):
    """Human-readable exact money in review outputs; canonical snapshots stay canonical."""
    def encode(item):
        if isinstance(item, Decimal):
            plain = format(item, "f")
            return plain.rstrip("0").rstrip(".") if "." in plain else plain
        if isinstance(item, (date, time)) and not isinstance(item, datetime):
            return item.isoformat()
        return json_value(item)
    return json.loads(json.dumps(value, default=encode, allow_nan=False))


def write_json(path, value):
    path.write_text(json.dumps(value, default=json_value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def check(checks, subtask, name, expected, actual):
    expected, actual = wire(expected), wire(actual)
    checks.append(dict(subtask=subtask, name=name, expected=expected, actual=actual, passed=actual == expected))


def rejection(checks, subtask, name, message_fragment, operation, exception=ValueError):
    try:
        operation()
    except exception as exc:
        actual = str(exc)
        checks.append(dict(subtask=subtask, name=name, expected=f"Rejected: {message_fragment}",
                           actual=actual, passed=message_fragment.lower() in actual.lower()))
    else:
        checks.append(dict(subtask=subtask, name=name, expected=f"Rejected: {message_fragment}",
                           actual="Accepted unexpectedly", passed=False))


def tzdb_version():
    for root in TZPATH:
        source = Path(root) / "tzdata.zi"
        if source.is_file():
            with source.open(encoding="utf-8") as stream:
                return stream.readline().strip()
    # Record a fingerprint of the actual zone file instead of guessing a version.
    for root in TZPATH:
        source = Path(root) / "America" / "New_York"
        if source.is_file():
            return "America/New_York sha256:" + sha256(source.read_bytes()).hexdigest()
    import importlib.metadata
    return "tzdata " + importlib.metadata.version("tzdata")


def fixture_bars(stamps, prices):
    result = []
    for number, (stamp, price) in enumerate(zip(stamps, prices, strict=True), 1):
        cells = (stamp.strftime("%m/%d/%Y"), stamp.strftime("%H:%M"), price, price, price, price, "0", "0", "0")
        result.append(Bar(number, stamp, cells[0], cells[1], *(D(value) for value in cells[2:]), cells))
    return result


def save_source(directory, bars, entries, closes):
    directory.mkdir(parents=True)
    strategy_text = inspect.getsource(DemonstrationStrategy)
    (directory / "strategy.py").write_text(strategy_text, encoding="utf-8")
    write_csv(directory / "dataset.csv", [dict(zip(
        ("Date", "Time", "Open", "High", "Low", "Close", "Volume", "UpVol", "DownVol"), bar.source_fields, strict=True)) for bar in bars],
        ("Date", "Time", "Open", "High", "Low", "Close", "Volume", "UpVol", "DownVol"))
    dataset_hash = sha256((directory / "dataset.csv").read_bytes()).hexdigest()
    metadata = {
        "dataset": {"id": "synthetic-" + dataset_hash[:16], "name": "Prop review synthetic fixture",
                    "sha256": dataset_hash, "row_count": len(bars), "source_timezone": "UTC", "symbol": "SYNTHETIC",
                    "instrument_settings": {"tick_size": ".25", "point_value": "10"}},
        "strategy": {"id": "prop_review_scheduled_intents", "source_sha256": sha256(strategy_text.encode()).hexdigest(),
                     "parameters": {"entries": entries, "closes": closes}},
        "selection": {"from_date": bars[0].timestamp_utc.date().isoformat(),
                      "to_date": bars[-1].timestamp_utc.date().isoformat(), "source_timezone": "UTC", "warmup": "none",
                      "row_count": len(bars), "start_utc": json_value(bars[0].timestamp_utc),
                      "end_utc": json_value(bars[-1].timestamp_utc), "first_source_bar_number": 1,
                      "last_source_bar_number": len(bars)}, "instrument_overrides": {},
    }
    store = RunStore(directory)
    staging = directory / "staging"
    manifest = generate_report(execute(iter(bars), DemonstrationStrategy(entries, closes), SETTINGS),
                               staging, SETTINGS, metadata=metadata, expected_bar_count=len(bars),
                               execution_assumption="same_close_full_fill")
    record = store.complete(uuid4().hex, staging, manifest)
    return store, record


def make_calendar(bars, profile):
    """Explicit windows for this fixture only, not inferred market coverage."""
    groups = {}
    for bar in bars:
        stamp = bar.timestamp_utc.astimezone(ZoneInfo(profile.session.timezone))
        label = stamp.date() + timedelta(days=stamp.time() >= time(18))
        groups.setdefault(label, []).append(bar.timestamp_utc)
    first, last = min(groups), max(groups)
    days = []
    for delta in range((last - first).days + 1):
        day = first + timedelta(days=delta)
        if day in groups:
            days.append(CalendarDay(day, "covered", (DataWindow(min(groups[day]), max(groups[day]), 60),)))
        else:
            days.append(CalendarDay(day, "closed" if day.weekday() >= 5 else "missing"))
    return SessionCalendar("synthetic-explicit-windows", profile.session, tzdb_version(), "explicit",
                           "Synthetic fixture only: the listed one-minute windows are complete; weekends explicitly closed. "
                           "This does not declare full exchange-session coverage for real data.", tuple(days))


def configuration(record, calendar, quantity):
    return SimulationConfig(
        source_backtest_id=record["id"], phase="evaluation", analysis="historical", observation_mode="bar_close",
        account_start_utc=calendar.bounds(calendar.days[0])[0], end_utc=calendar.bounds(calendar.days[-1])[2],
        instrument="SYNTHETIC", currency="USD", contract_limit_weight=D("1"),
        contract_limit_source_url=DECLARATION.contract_limit_source_url, quantity=quantity,
        calendar_id=calendar.id, calendar_sha256=calendar.sha256, timezone_data_version=calendar.timezone_data_version,
        coverage_assumption=calendar.coverage_assumption, fees=UserFees("USD", attempt_fee=D("0")),
    )


def specification_review(path, checks):
    content = SPECIFICATION.read_bytes()
    text = content.decode("utf-8")
    (path / "specification.md").write_bytes(content)
    design = ["completed backtest", "session adapter", "deterministic prop-account engine",
              "Monte Carlo / sizing analysis", "saved results", "portal"]
    block = text.split("```text\n", 1)[1].split("```", 1)[0]
    check(checks, 1, "One documented pipeline", design, [line.strip().removeprefix("-> ") for line in block.strip().splitlines()])
    for title in ("Holdout leakage", "Missing staged-sizing DLL", "Excursion normalization", "Different engine behavior",
                  "Calendar approximations", "Perfect-threshold liquidation"):
        check(checks, 1, title + " documented", True, f"**{title}.**" in text)
    check(checks, 1, "Pinned notebook identity present in specification", True, NOTEBOOK_SHA256 in text)
    return dict(sha256=sha256(content).hexdigest(), notebook_sha256=NOTEBOOK_SHA256,
                notebook_reviewed_on="2026-10-25", notebook_check="Pinned review identity; this demonstration does not fetch Drive again.",
                design=design, deliverable="docs/prop_simulation.md")


def rules_review(profile, checks):
    snapshot = resolve_profile(profile)
    e, f = profile.evaluation, profile.funded
    check(checks, 2, "Evaluation target / DD / daily limit / calendar days / contracts",
          ["3000", "2000", "1000", 30, 6], [e.profit_target, e.drawdown.amount, e.limits.daily_loss_limit, e.access_calendar_days, e.limits.max_contracts])
    check(checks, 2, "Separate funded drawdown lock", "100", f.drawdown.lock_profit)
    check(checks, 2, "Payout ladder", ["1500", "1500", "2000", "2500", "2500", "3000"], f.payouts.ladder)
    platforms = []
    for platform in ("rithmic", "tradovate", "wealthcharts"):
        lock = get_profile("apex_50k_eod_" + platform).evaluation.drawdown.lock_profit
        check(checks, 2, f"{platform} evaluation lock", None if platform == "tradovate" else "3000", lock)
        platforms.append(dict(platform=platform, evaluation_lock_profit=wire(lock)))
    tiers = []
    for profit, contracts, dll in (("-0.01", 2, "1000"), ("1499.99", 2, "1000"), ("1500", 3, "1000"),
                                   ("2999.99", 3, "1000"), ("3000", 4, "2000"), ("5999", 4, "2000"), ("6000", 4, "3000")):
        tier = f.tier_for_profit(D(profit))
        actual = [tier.limits.max_contracts, wire(tier.limits.daily_loss_limit)]
        check(checks, 2, "Tier at prior-session profit " + profit, [contracts, dll], actual)
        tiers.append(dict(profit=profit, max_contracts=actual[0], daily_loss_limit=actual[1]))
    check(checks, 2, "Deterministic profile hash", snapshot.profile_sha256, resolve_profile(get_profile(profile.id)).profile_sha256)
    saved = snapshot.to_json()
    changed_template = replace(profile, version="1.0.1", evaluation=replace(
        e, limits=replace(e.limits, daily_loss_limit=D("1100"))))
    check(checks, 2, "Saved snapshot survives a changed template", snapshot.profile_sha256, ResolvedProfile.from_json(saved).profile_sha256)
    check(checks, 2, "Changed template changes its own hash", True, resolve_profile(changed_template).profile_sha256 != snapshot.profile_sha256)
    tampered = json.loads(saved)
    tampered["profile"]["version"] = "1.0.1"
    rejection(checks, 2, "Tampered snapshot rejected", "hash mismatch", lambda: ResolvedProfile.from_json(json.dumps(tampered)))
    rejection(checks, 2, "Overlapping tier boundaries rejected", "strictly increasing",
              lambda: replace(f, tiers=(f.tiers[0], f.tiers[0], *f.tiers[2:])))
    return dict(snapshot=snapshot.to_dict(), tiers=tiers, platforms=platforms,
                evaluation=wire(asdict(e)), funded=wire(asdict(f)),
                evidence=wire([asdict(item) for item in profile.evidence]),
                sources=wire([asdict(item) for item in profile.sources]), assumptions=profile.assumptions.to_dict())


def build_review(path, review_id, platform, quantity):
    checks = []
    profile = get_profile("apex_50k_eod_" + platform)
    specification = specification_review(path, checks)
    rules = rules_review(profile, checks)
    stamps = [datetime(2026, 1, day, 14, minute, tzinfo=timezone.utc) for day in (5, 6, 7) for minute in (0, 1, 2)]
    bars = fixture_bars(stamps, ["100"] * 3 + ["100", "100.5", "102"] + ["100"] * 3)
    store, record = save_source(path / "sources" / "arithmetic", bars, {4: 2}, [6])
    calendar = make_calendar(bars, profile)
    config = configuration(record, calendar, quantity)
    resolved = resolve_simulation(config, profile)
    write_json(path / "profile.json", rules["snapshot"])
    write_json(path / "simulation.json", resolved.to_dict())
    (path / "calendar.json").write_text(calendar.to_json() + "\n", encoding="utf-8")
    rejection(checks, 2, "Fractional quantity rejected", "must be int", lambda: replace(config, quantity=1.5))
    rejection(checks, 2, "Funded phase rejects evaluation fees", "activation_fee", lambda: replace(config, phase="funded"))
    funded_config = replace(config, phase="funded", fees=UserFees("USD", activation_fee=D("0")))
    check(checks, 2, "Funded configuration resolves independently", "funded", resolve_simulation(funded_config, profile).config.phase)
    with prepare_backtest(store, resolved, calendar, DECLARATION) as source:
        sessions = wire([asdict(session) for session in source.sessions()])
        observations = []
        for session in source.sessions():
            for mode in ("trade_close", "bar_close"):
                observations.extend(dict(trading_date=session.trading_date.isoformat(), mode=mode, **wire(asdict(mark)))
                                    for mark in source.observations(session.trading_date, mode=mode))
        trade, = source.trades()
        trade = wire(asdict(trade))
        source_snapshot = source.snapshot.to_dict()
        source_hash = source.snapshot.sha256
    write_json(path / "source.json", source_snapshot)
    check(checks, 3, "Covered zero-trade sessions retained", [0, 1, 0], [s["trade_count"] for s in sessions])
    check(checks, 3, "Every declared covered bar retained", [3, 3, 3], [s["bar_count"] for s in sessions])
    check(checks, 3, "Original source quantity retained", 2, trade["source"]["contracts"])
    expected = {1: ["15", "2", "5", "13"], 2: ["30", "4", "10", "26"]}[quantity]
    check(checks, 3, "Gross / commissions / informational slippage / net (costs once)", expected,
          [trade[key] for key in ("gross_pnl", "total_commissions", "slippage_cost", "net_pnl")])
    marks = [m for m in observations if m["mode"] == "bar_close" and m["trade_number"] is not None]
    check(checks, 3, "Bar-close cumulative trade-relative P&L", ["-3.5", "1.5", "13"] if quantity == 1 else ["-7", "3", "26"],
          [m["equity_change"] for m in marks])
    check(checks, 3, "Trade-close stream contains one completed-trade observation", [expected[-1]],
          [m["equity_change"] for m in observations if m["mode"] == "trade_close"])
    check(checks, 3, "Source absolute equity preserved", "10026", marks[-1]["source_equity"])
    check(checks, 3, "Actual saved metadata preserved", record["run_metadata"], json.loads(source_snapshot["manifest_json"])["run_metadata"])

    def prepare_other(other_store=store, other_record=record, other_calendar=calendar, declaration=DECLARATION):
        settings = resolve_simulation(configuration(other_record, other_calendar, quantity), profile)
        with prepare_backtest(other_store, settings, other_calendar, declaration):
            pass

    missing = replace(calendar, days=(calendar.days[0], replace(calendar.days[1], status="missing", windows=()), calendar.days[2]))
    rejection(checks, 3, "Missing coverage rejected, not zero trading", "coverage", lambda: prepare_other(other_calendar=missing), InputError)
    variable_store, variable_record = save_source(path / "sources" / "variable", bars, {1: 2, 4: 1}, [3, 6])
    rejection(checks, 3, "Variable source quantities rejected", "Variable source quantities", lambda: prepare_other(variable_store, variable_record), InputError)
    overnight_store, overnight_record = save_source(path / "sources" / "overnight", bars, {3: 2}, [4])
    rejection(checks, 3, "Overnight exposure rejected", "session", lambda: prepare_other(overnight_store, overnight_record), InputError)
    rejection(checks, 3, "Unsupported currency declaration rejected", "Instrument declaration does not match",
              lambda: prepare_other(declaration=replace(DECLARATION, currency="EUR")), InputError)

    dst_bars = fixture_bars([datetime(2026, 3, 6, 14, tzinfo=timezone.utc), datetime(2026, 3, 9, 0, tzinfo=timezone.utc)], ["100", "100"])
    dst_store, dst_record = save_source(path / "sources" / "dst", dst_bars, {}, [])
    dst_calendar = make_calendar(dst_bars, profile)
    with prepare_backtest(dst_store, resolve_simulation(configuration(dst_record, dst_calendar, quantity), profile), dst_calendar, DECLARATION) as source:
        dst_sessions = wire([asdict(s) for s in source.sessions()])
        sunday_marks = list(source.observations(date(2026, 3, 9)))
    check(checks, 3, "Sunday 20:00 New York retained in Monday session", 1, len(sunday_marks))
    check(checks, 3, "DST changes session open UTC hour", [23, 22],
          [datetime.fromisoformat(s["open_utc"].replace("Z", "+00:00")).hour for s in (dst_sessions[0], dst_sessions[-1])])
    check(checks, 3, "Declared closed dates remain distinct from covered dates", ["covered", "closed", "closed", "covered"],
          [s["status"] for s in dst_sessions])
    write_csv(path / "sessions.csv", sessions, sessions[0].keys())
    write_csv(path / "observations.csv", observations, observations[0].keys())
    write_csv(path / "checks.csv", [dict(c, actual=json.dumps(c["actual"]), expected=json.dumps(c["expected"])) for c in checks], checks[0].keys())
    result = dict(format_version=1, id=review_id, created_at_utc=json_value(datetime.now(timezone.utc)),
                  platform=platform, quantity=quantity, synthetic=True, all_passed=all(c["passed"] for c in checks),
                  specification=specification, rules=rules, checks=checks,
                  adapter=dict(sessions=sessions, observations=observations, trade=trade, dst_sessions=dst_sessions,
                               source_sha256=source_hash, source_snapshot=source_snapshot,
                               settings_sha256=resolved.settings_sha256, calendar_sha256=calendar.sha256),
                  limitations=["Synthetic review fixtures only; no strategy performance or account outcomes are simulated.",
                               "Fees are explicitly zero for the fixture, supplied by the demonstration, not Apex prices.",
                               "Bar-close P&L is cumulative within each trade; do not sum these marks.",
                               "Rules retain their recorded retrieval date and unresolved source conflict.",
                               "No account engine, Monte Carlo, payouts, or measured excursions are implemented by this review."],
                  exports=sorted(EXPORTS))
    write_json(path / "review.json", result)
    with ZipFile(path / "bundle.zip", "w", ZIP_DEFLATED) as bundle:
        for item in sorted(path.rglob("*")):
            if item.is_file() and item.name != "bundle.zip" and item.suffix != ".sqlite3":
                bundle.write(item, item.relative_to(path))
    return result


def create_review(root, platform, quantity):
    """Publish only a complete review, even if a demonstration assertion fails."""
    if platform not in {"rithmic", "tradovate", "wealthcharts"} or type(quantity) is not int or quantity not in (1, 2):
        raise ValueError("Choose a supported platform and integer demonstration quantity 1 or 2.")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    review_id = uuid4().hex
    with TemporaryDirectory(prefix=".staging-", dir=root) as temporary:
        path = Path(temporary) / "review"
        path.mkdir()
        result = build_review(path, review_id, platform, quantity)
        path.rename(root / review_id)
    pointer = root / (".latest-" + review_id)
    pointer.write_text(review_id, encoding="ascii")
    os.replace(pointer, root / "latest")
    return result
