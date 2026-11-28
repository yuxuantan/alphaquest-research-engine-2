import csv
import json
from itertools import combinations, product
from math import sqrt
from pathlib import Path
from statistics import mean, median
from time import monotonic, sleep

from fastapi.testclient import TestClient

from alphaquest.app import create_app
from alphaquest.prop import desk_basket, desk_recommendation
from alphaquest.prop_desk import RecommendationLaunch, prepare

root = Path(__file__).parent
reference = root / 'data/prop_analyses/245639096bad4e07a6af8115b0161c69/report.json'
app = create_app(root / 'data/datasets.sqlite3')
result = {}


def metrics_from_paths(paths, phase):
    if phase == 'evaluation':
        pass_days = [p['trading_sessions'] for p in paths if p['outcome'] == 'passed']
        return len(pass_days) / len(paths), 0., median(pass_days) if pass_days else None
    receipt_totals = [sum(amount for _, amount in p['trader_payouts']) for p in paths]
    first_days = [p['trader_payouts'][0][0] for p in paths if p['trader_payouts']]
    return len(first_days) / len(paths), mean(receipt_totals), median(first_days) if first_days else None


def size_key(row, phase):
    value = row['probability'] if phase == 'evaluation' else row['receipts']
    return (-value, sum(row['allocation']),
            (row['median_day'] or float('inf')) if phase == 'evaluation' else 0, row['allocation'])


def rank(rows, phase, paths):
    largest = max(r['probability'] for r in rows)
    threshold = largest - sqrt(largest * (1-largest) / paths)
    def order(row):
        p = row['probability']
        if p >= threshold:
            return 0, row['median_day'] or float('inf'), -p, sum(row['allocation']), row['subset']
        return 1, 0, -p, sum(row['allocation']), row['subset']
    return sorted(rows, key=order)


def score_columns(phase, prefix, metrics):
    if phase == 'evaluation':
        rates = metrics.get('probabilities', {})
        values = dict(success=rates.get('passed'), breach=rates.get('breached'),
                      median_success_day=metrics.get('median_trading_days_to_target'),
                      mean_receipts_usd=None, open_at_cutoff=None)
    else:
        values = dict(success=metrics.get('probability_any_payout'), breach=metrics.get('probability_breach'),
                      median_success_day=(metrics.get('milestones') or [{}])[0].get('median_trading_day'),
                      mean_receipts_usd=metrics.get('mean_trader_receipts'),
                      open_at_cutoff=metrics.get('open_at_cutoff'))
    return {f'{prefix}_{name}': value for name, value in values.items()}


def allocation_results(model, candidates, scores, members, phase, path_count, exact_winners):
    selected_ids = {row['candidate'] for row in model['ranking']}
    exact_keys = {(row['subset'], row['allocation']) for row in exact_winners}
    normal = {(group['id'], tuple(row['targets'])): row for group in model['groups']
              for row in group['candidates']}
    assert normal.keys() <= candidates.keys()
    for key, row in sorted(candidates.items(), key=lambda item: (item[0][0], sum(item[0][1]), item[0][1])):
        saved = normal.get(key, {})
        saved_paths = saved.get('paths', 0)
        status = 'full_paths' if saved_paths == path_count else 'screen_only' if saved_paths else 'untested'
        normal_metrics = saved.get('metrics', {})
        if status == 'full_paths':
            assert score_columns(phase, 'same', normal_metrics) == score_columns(phase, 'same', scores[key])
        yield dict(phase=phase, success_definition='passed' if phase == 'evaluation' else 'any_payout',
                   subset_id=row['subset'],
                   member_backtest_ids=' '.join(members[i]['source_backtest_id'] for i in row['members']),
                   allocation_mnq='+'.join(map(str, row['allocation'])), total_mnq=sum(row['allocation']),
                   normal_status=status, normal_paths=saved_paths, normal_subset_winner=saved.get('id') in selected_ids,
                   exhaustive_paths=path_count, exhaustive_subset_winner=key in exact_keys,
                   **score_columns(phase, 'normal', normal_metrics),
                   **score_columns(phase, 'exhaustive', scores[key]))


def main():
    all_allocations = []
    with TestClient(app) as client:
        response = client.get('/api/prop-desk/sources?limit=100')
        response.raise_for_status()
        eligible = {s['id']: s['oos']['id'] for s in response.json()['items'] if s.get('oos')}
        members = [m for m in json.loads(reference.read_text())['configuration']['members']
                   if eligible.get(m['source_backtest_id']) == m['oos_backtest_id']][:4]
        assert len(members) == 4, 'Reference pool availability changed'
        base = dict(profile_id='apex-50k-eod', minimum_members=1, minimum_micros=4, maximum_micros=6,
                    overlap_policy='sequential_mae', allocation_search='individual', members=members)
        for phase in ('evaluation', 'funded'):
            declaration = dict(base, phase=phase)
            start = monotonic()
            launched = client.post('/api/prop-desk/recommendations', json=declaration)
            launched.raise_for_status()
            job = launched.json()
            while job['status'] in ('queued','running'):
                assert monotonic() - start < 120, job
                sleep(.15)
                job = client.get('/api/prop-desk/'+job['id']).json()
            assert job['status'] == 'complete', job
            report = client.get('/api/prop-desk/'+job['id']).json()['report']
            model = report['recommendation']
            body = RecommendationLaunch.model_validate(declaration)
            config = body.resolved()
            assert config == report['configuration']
            prepared = prepare(app.state.runs, app.state.prop_analyses, body, config, app.state.store)
            assert prepared['is_days'] == model['is_days']
            seeds = desk_recommendation.path_seeds(prepared['simulation'])
            expected_subsets = [subset for count in range(1, len(members) + 1)
                                for subset in combinations(range(len(members)), count)]
            assert [tuple(group['members']) for group in model['groups']] == expected_subsets
            by_subset = {}
            candidates = {}
            scores = {}
            for group in model['groups']:
                subset = tuple(group['members'])
                books = [prepared['is_books'][i] for i in subset]
                weights = [members[i]['weight'] for i in subset]
                rows = by_subset[group['id']] = []
                for allocation in product(range(1, 7), repeat=len(subset)):
                    if not 4 <= sum(allocation) <= 6:
                        continue
                    trades, _ = desk_basket.admitted(books, prepared['is_days'], weights, allocation, sequential=True)
                    computed, paths, _ = desk_recommendation.evaluate(trades, allocation, prepared, config, seeds)
                    probability, receipts, median_day = metrics_from_paths(paths, phase)
                    if phase == 'evaluation':
                        assert computed['probabilities']['passed'] == probability
                        assert computed['median_trading_days_to_target'] == median_day
                    else:
                        assert computed['probability_any_payout'] == probability
                        assert abs(computed['mean_trader_receipts'] - receipts) < 1e-8
                        assert computed['milestones'][0]['median_trading_day'] == median_day
                    row = dict(subset=group['id'], members=subset, allocation=allocation, probability=probability,
                               receipts=receipts, median_day=median_day)
                    candidates[(group['id'], allocation)] = row
                    scores[(group['id'], allocation)] = computed
                    rows.append(row)
                assert len(rows) == group['feasible']
            assert len(candidates) == model['workload']['feasible'] == 175
            actual_chosen = []
            full_scored = 0
            for group in model['groups']:
                confirmed = [r for r in group['candidates'] if r['paths'] == len(seeds)]
                full_scored += len(confirmed)
                confirmed_rows = [candidates[(group['id'], tuple(r['targets']))] for r in confirmed]
                saved = next(r for r in model['ranking'] if r['combination'] == group['id'])
                selected = next(r for r in confirmed if r['id']==saved['candidate'])
                chosen = candidates[(group['id'], tuple(selected['targets']))]
                assert abs(chosen['probability'] - saved['score']) < 1e-12
                assert abs((chosen['probability'] if phase == 'evaluation' else chosen['receipts']) - saved['size_score']) < 1e-8
                assert chosen['median_day'] == saved['median_days']
                assert chosen == min(confirmed_rows, key=lambda r: size_key(r, phase))
                actual_chosen.append(chosen)
            actual_order = rank(actual_chosen, phase, len(seeds))
            assert [r['subset'] for r in actual_order] == [r['combination'] for r in model['ranking']]
            exhaustive_best_by_subset = [min(rows, key=lambda r: size_key(r, phase)) for rows in by_subset.values()]
            exhaustive_order = rank(exhaustive_best_by_subset, phase, len(seeds))
            all_allocations.extend(allocation_results(model, candidates, scores, members, phase, len(seeds),
                                                      exhaustive_best_by_subset))
            comparison = dict(
                phase=phase, existing_allocation_search=report['configuration']['allocation_search'],
                normal_report_id=job['id'], ranking_sha256=model['ranking_sha256'],
                source_ids=[m['source_backtest_id'] for m in members], profile=base['profile_id'],
                bounds=[4,6], is_days=len(prepared['is_days']), first_session=prepared['is_days'][0],
                last_session=prepared['is_days'][-1], horizon=config['observation_sessions'], paths_per_full_row=len(seeds),
                workload=model['workload'], full_scored=full_scored,
                production_winner=actual_order[0], exhaustive_under_current_policy=exhaustive_order[0],
                max_probability_over_entire_grid=max(candidates.values(), key=lambda r: (r['probability'], -sum(r['allocation']))),
                max_receipts_over_entire_grid=max(candidates.values(), key=lambda r: (r['receipts'], -sum(r['allocation']))) if phase=='funded' else None,
                same_subset_allocations=sum(a == b for a,b in zip(actual_chosen, exhaustive_best_by_subset)),
                production_ranking=actual_order, exhaustive_ranking=exhaustive_order,
                elapsed_seconds=round(monotonic()-start,2))
            result[phase] = comparison
            (root/'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps({k:v for k,v in comparison.items() if k not in ('production_ranking','exhaustive_ranking')}, indent=2), flush=True)
    with (root/'all-allocations.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=list(all_allocations[0]))
        writer.writeheader()
        writer.writerows(all_allocations)


if __name__ == "__main__":
    main()
