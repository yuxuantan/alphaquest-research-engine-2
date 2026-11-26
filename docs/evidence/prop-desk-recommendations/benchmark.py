"""Run the current product API against an isolated copy of the saved catalogue."""
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
from alphaquest.app import create_app


def main(root):
    existing = json.loads((root/'data/prop_analyses/245639096bad4e07a6af8115b0161c69/report.json').read_text())
    config = dict(profile_id='apex-50k-eod', minimum_members=1, minimum_micros=4, maximum_micros=6,
                  overlap_policy='sequential_mae')
    with TestClient(create_app(root/'data/datasets.sqlite3')) as client:
        catalogue = client.get('/api/prop-desk/sources?limit=100')
        catalogue.raise_for_status()
        verified = {s['id']: s['oos']['id'] for s in catalogue.json()['items'] if s.get('oos')}
        members = [m for m in existing['configuration']['members']
                   if verified.get(m['source_backtest_id']) == m['oos_backtest_id']][:4]
        print('Verified members', len(members), flush=True)
        if len(members) != 4:
            raise SystemExit('Four currently qualified sources are unavailable on this reference pool.')

        def run(declaration):
            started = time.perf_counter()
            response = client.post('/api/prop-desk/recommendations', json=declaration)
            if not response.is_success:
                raise RuntimeError(response.text)
            job = response.json()
            while job['status'] in ('queued','running'):
                time.sleep(.10)
                job = client.get('/api/prop-desk/'+job['id']).json()
                if time.perf_counter() - started > 115:
                    raise RuntimeError(job)
            if job['status'] != 'complete':
                raise RuntimeError(job)
            if not job.get('report'):
                job = client.get('/api/prop-desk/'+job['id']).json()
            return job, time.perf_counter() - started

        timings = {}
        for phase in ('evaluation', 'funded'):
            _, smaller = run(dict(config, phase=phase, members=members[:3]))
            terms = dict(config, phase=phase, members=members)
            job, elapsed = run(terms)
            _, reopen = run(terms)
            direct_start = time.perf_counter()
            client.get('/api/prop-desk/' + job['id']).raise_for_status()
            direct = time.perf_counter() - direct_start
            rec = job['report']['recommendation']
            timings[phase] = dict(three_strategy_seconds=smaller, four_strategy_seconds=elapsed,
                repeat_run_seconds=reopen, saved_reopen_seconds=direct, observed_is_sessions=len(rec['is_days']), bounds=[4,6],
                workload=rec['workload'], stages=rec['timing'], paths_per_finalist=rec['ranking'][0]['path_count'], ranking_sha256=rec['ranking_sha256'])
            print(phase, timings[phase], flush=True)
            (root/'real-timing.json').write_text(json.dumps(timings, indent=2))


if __name__ == '__main__':
    main(Path(__file__).parent)
