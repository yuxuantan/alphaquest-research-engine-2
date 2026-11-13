"""IS-only automatic family selection over existing sealed phase results.

This chooses a small frozen family, not a new optimizer or account model.
Complete Pareto/ranking membership remains available in the original IS report.
"""
from copy import deepcopy
from hashlib import sha256
from math import isfinite
from pathlib import Path
from .optimization_cache import digest

POLICY=dict(version='prop-sim-auto-selection-v1',evaluation_maximum=3,
    evaluation_fast_time_multiplier=1.25,funded_maximum=2,funded_receipts_retention=.95,
    tie_break='smaller_micros_then_candidate_id',data_role='IS_only',
    unresolved='exclude_without_blocking_resolved_candidates',duplicates='collapse_within_phase')


def identity():
    return dict(policy=deepcopy(POLICY),source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def choose(report,phase):
    if phase not in ('evaluation','funded'):raise ValueError('Unknown automatic selection phase.')
    if report['phase']!=phase:raise ValueError('IS report phase differs from selection phase.')
    if report.get('assessment'):raise ValueError('Automatic sizing must use an IS search report, not assessment outcomes.')
    calc=report['calculations'];members=set(calc['frontier'] if phase=='evaluation' else calc['ranking'])
    metrics=('cost_per_funded','expected_calendar_days_to_funded') if phase=='evaluation' else ('expected_funded_cash_payouts_within_horizon',)
    rows=[r for r in calc['candidates'] if r['candidate_id'] in members and r['status']=='estimated'
        and r.get('feasible') is not False and all(type(r['metrics'].get(k)) in (int,float)
            and isfinite(r['metrics'][k]) and (r['metrics'][k]>=0 if k=='cost_per_funded' else r['metrics'][k]>0) for k in metrics)]
    def size(r):return r['manifest']['configuration']['micros']
    def tie(r):return size(r),r['candidate_id']
    selected={}
    def add(row,role):
        selected.setdefault(row['candidate_id'],dict(candidate_id=row['candidate_id'],micros=size(row),roles=[],
            is_metrics={k:row['metrics'][k] for k in metrics}))['roles'].append(role)
    if rows and phase=='evaluation':
        cheapest=min(rows,key=lambda r:(r['metrics'][metrics[0]],*tie(r)))
        fastest=min(rows,key=lambda r:(r['metrics'][metrics[1]],*tie(r)))
        fast=[r for r in rows if r['metrics'][metrics[1]]<=fastest['metrics'][metrics[1]]*POLICY['evaluation_fast_time_multiplier']]
        efficient=min(fast,key=lambda r:(r['metrics'][metrics[0]],*tie(r)))
        for row,role in ((cheapest,'Lowest acquisition cost'),(fastest,'Fastest funding'),(efficient,'Lowest cost within 25% of fastest')):add(row,role)
    elif rows:
        best=min(rows,key=lambda r:(-r['metrics'][metrics[0]],*tie(r)))
        near=[r for r in rows if r['metrics'][metrics[0]]>=best['metrics'][metrics[0]]*POLICY['funded_receipts_retention']]
        alternative=min(near,key=tie)
        add(best,'Highest mean trader receipts');add(alternative,'Smallest size retaining 95% of peak receipts')
    result=dict(phase=phase,selection_identity=identity(),status='selected' if selected else 'no_eligible_candidates',
        candidates=list(selected.values()),excluded_count=len(calc['candidates'])-len(rows),
        interpretation='Automatic IS-only selection of resolved eligible point estimates; no OOS tuning or certified superiority. Lower exposure does not guarantee lower breach probability.')
    result['selection_sha256']=digest(result)
    return result
