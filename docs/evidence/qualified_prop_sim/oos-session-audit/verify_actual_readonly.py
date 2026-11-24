"""Read existing report/catalogue only; no calculation, selection or API writes."""
import json
import sqlite3
import urllib.request
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from alphaquest.prop.phase_dispatch import module_for, implementations_compatible
from alphaquest.prop.phase_search import check_candidates, saved_oos_period

BASE = 'http://localhost:8000'
SIMULATION = '2d19909ce7b3404ca73adb534d6a8d2a'


def get(path):
    with urllib.request.urlopen(BASE+path) as response:
        return json.load(response)


class ReadOnlyRuns:
    root = Path('data/backtest_runs').resolve()

    @contextmanager
    def connect(self):
        db = sqlite3.connect('file:'+str(self.root.parent/'backtests.sqlite3')+'?mode=ro', uri=True)
        try:
            yield db
        finally:
            db.close()


def main():
    source = ReadOnlyRuns()
    saved = get('/api/prop-sim/'+SIMULATION)
    observed = get('/api/backtests/'+saved['qualification']['oos_report_id'])
    results = []
    for phase, cid in saved['campaign_ids'].items():
        package = get('/api/research-campaigns/'+cid+'/exports/frozen_package.json')
        campaign = get('/api/research-campaigns/'+cid)
        module = module_for(phase)
        current_is = module.check_search(source, module.parse_request(campaign['manifest']['request']))
        assert [c['candidate_id'] for c in current_is] == [c['candidate_id'] for c in campaign['manifest']['source_checks']]
        configs, mappings = [], []
        for definition in package['candidate_definitions']:
            manifest = definition['manifest']
            config = deepcopy(manifest['configuration'])
            config['source']['source_backtest_id'] = observed['id']
            config['period'] = saved_oos_period(observed)
            configs.append(config)
            mappings.append(dict(source_id=observed['id'], frozen_candidate_id=definition['candidate_id'], frozen_manifest=manifest))
        raw = dict(package['search_settings'], candidates=configs, source_backtest_id=observed['id'])
        module = module_for(phase)
        assert implementations_compatible(package['implementation'], module.implementation_identity())
        checks = check_candidates(source, module.parse_request(raw), dict(kind='oos', sources=mappings, frozen_package=package))
        assert {c['frozen_candidate_id'] for c in checks} == set(package['candidate_ids'])
        results.append(dict(phase=phase, compatible=True, is_source_identities_unchanged=True, admitted=len(checks),
            sizes=[c['manifest']['configuration']['micros'] for c in checks],
            period=configs[0]['period'], package_sha256=package['package_sha256'],
            original_phase_search_sha256=package['implementation']['files']['phase_search.py'],
            current_phase_search_sha256=module.implementation_identity()['files']['phase_search.py']))
    output = dict(simulation_id=SIMULATION, checks=results, read_only=True, calculation_started=False,
        storage='SQLite mode=ro; existing source files read only; GET API requests only')
    Path(__file__).with_name('actual-run-readonly-admission.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
