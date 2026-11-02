"""Compile the actual C# calendar helper and compare every reviewed session to AQ.

This does not compile or simulate the PowerLanguage signal: MC's SDK/host is
required for that separate qualification. No DLL substitutes or VM are used.
"""
import argparse
import csv
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

from alphaquest.session_calendar import calendar_path, load_calendar


ROOT = Path(__file__).resolve().parents[1]


def review(output, dotnet):
    output.mkdir(parents=True, exist_ok=False)
    project = ROOT / 'tests/multicharts_calendar/CalendarCheck.csproj'
    env = {**os.environ, 'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1'}
    built = subprocess.run([dotnet, 'build', str(project), '--nologo', '-v', 'quiet'],
                           capture_output=True, text=True, env=env, check=True)
    (output / 'build.txt').write_text(built.stdout + built.stderr)
    binary = project.parent / 'bin/Debug/net8.0/CalendarCheck.dll'

    def run(path, *args):
        return subprocess.run([dotnet, str(binary), str(path), *args],
                              capture_output=True, text=True, env=env)

    calendar = load_calendar()
    actual = run(calendar_path())
    assert actual.returncode == 0, actual.stderr
    (output / 'csharp-plans.csv').write_text(actual.stdout)
    lines = actual.stdout.splitlines()
    assert lines[0] == 'sha256,' + calendar.sha256
    rows = list(csv.DictReader(lines[1:]))
    expected_count = ((calendar.end - calendar.start).days + 1) * 2
    assert len(rows) == expected_count
    for row in rows:
        plan = calendar.plan(date.fromisoformat(row['session_date']), int(row['eod']))
        assert row['kind'] == plan.kind, row
        assert row['close'] == (plan.close.strftime('%H:%M') if plan.close else ''), row
        assert row['cutoff'] == (plan.cutoff.strftime('%H:%M') if plan.cutoff else ''), row
        expected = ('True', 'False', 'True', 'False') if plan.cutoff else ('False',) * 4
        assert tuple(row[k] for k in ('signal_before', 'signal_last', 'fill_before', 'fill_at')) == expected, row
        if plan.cutoff:
            assert plan.allows(plan.cutoff - timedelta(minutes=1))
            assert not plan.allows(plan.cutoff)

    rejections = []
    with tempfile.TemporaryDirectory(prefix='aq-csharp-calendar-') as temporary:
        path = Path(temporary) / 'calendar.csv'
        source_rows = list(csv.DictReader(calendar_path().open()))
        for name, change in (
            ('wrong_timezone', {'timezone': 'CST'}),
            ('bad_time', {'close_time_local': '25:00'}),
            ('full_close_with_time', {'closure_type': 'full_close', 'close_time_local': '12:00'}),
            ('inconsistent_coverage', {'coverage_end': '2026-12-31'}),
            ('missing_source', {'source_url': ''}),
            ('bad_review_date', {'verified_on': '11/02/2026'}),
            ('duplicate_day', {'session_date': source_rows[0]['session_date']}),
        ):
            changed = [dict(row) for row in source_rows]
            changed[1].update(change)
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=source_rows[0])
                writer.writeheader(); writer.writerows(changed)
            failed = run(path)
            assert failed.returncode != 0, name
            try:
                load_calendar(path)
            except ValueError:
                pass
            else:
                raise AssertionError('AQ accepted ' + name)
            rejections.append({'case': name, 'csharp_error': failed.stderr.strip()})
        for day in ('2015-12-31', '2026-11-03'):
            failed = run(calendar_path(), day)
            assert failed.returncode != 0 and 'cover' in failed.stderr.lower(), failed.stderr
            rejections.append({'case': 'unknown_' + day, 'csharp_error': failed.stderr.strip()})
        source_rows[0]['source_note'] += ' CSV quoted comma, escaped "quote" and\nnewline.'
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=source_rows[0], quoting=csv.QUOTE_ALL)
        writer.writeheader(); writer.writerows(source_rows)
        path.write_bytes(b'\xef\xbb\xbf' + stream.getvalue().encode())
        accepted = run(path)
        assert accepted.returncode == 0, accepted.stderr
        assert accepted.stdout.splitlines()[0] == 'sha256,' + load_calendar(path).sha256
        assert accepted.stdout.splitlines()[1:] == lines[1:]

    result = dict(calendar_sha256=calendar.sha256, matching_session_cutoff_cases=len(rows),
                  cutoff_boundary_checks=len(rows) * 4, rejected_cases=rejections,
                  bom_quoted_commas_quotes_newlines_accepted=True,
                  compiled_source='multicharts/ORB_VWAP_CONT__NQ_1M_PIVOT_V01.cs',
                  language_version='C# 5', host='.NET 8 standalone calendar helper only',
                  full_multicharts_compile_backtest_live_qualified=False)
    (output / 'verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    review(args.output.resolve(), args.dotnet)
