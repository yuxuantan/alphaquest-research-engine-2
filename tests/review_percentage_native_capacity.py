"""Explicit bounded M0 experiment, not a production simulation or qualification.

Run: .venv/bin/python tests/review_percentage_native_capacity.py --output /tmp/capacity.json
Uses synthetic actual-bar fixtures and existing phase owners. No live catalogue,
job, source, threshold or report is changed. Not collected as a pytest test.
"""
import argparse
from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import resource
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_native_draws import catalog,CONFIG
from test_native_forecast_profiles import targets
from native_replay_fixtures import parameters
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
from alphaquest.prop.native_draws import NativePathPreparation
from alphaquest.prop.native_replay import NativeForecastRequest
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,SizingConfiguration,rule_version
from alphaquest.prop.evaluation_profiles import forecast_native_evaluation
from alphaquest.prop.funded_profiles import forecast_native_funded
from alphaquest.prop.evaluation_optimization import SequentialRetry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--paths',type=int,choices=range(2,33),default=4)
    args=parser.parse_args()
    started=perf_counter();c=catalog()
    factory=lambda:VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
    prep_started=perf_counter();prepared=NativePathPreparation(c,factory,CONFIG)
    prep_seconds=perf_counter()-prep_started
    f=NativeForecastRequest(model='observed_contiguous_blocks_with_prior_prefix_v1',
        simulations=args.paths,seed=1729,block_sessions=1,horizon_calendar_days=3,capture_paths=1,
        calendar=dict(start_dates=['2026-01-12'],coverage_end='2026-01-16',closures=[],
            timezone='America/Chicago',version='synthetic-capacity-only-v1'))
    target=targets(f)
    sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='current_account_balance'),
        '50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
    rows=[]
    for profile_id in ('apex-50k-eod','lucidflex-50k'):
        for phase in ('evaluation','funded'):
            common=dict(forecast=f)
            def run(preparation):
                if phase=='evaluation':
                    return forecast_native_evaluation(c,target,factory,CONFIG,
                        EvaluationProfile(profile_id,rule_version(profile_id),'49','129' if profile_id=='apex-50k-eod' else '0'),
                        sizing,40,retry=SequentialRetry(activation_delay_sessions=0),preparation=preparation,**common)
                return forecast_native_funded(c,target,factory,CONFIG,FundedProfile(profile_id,rule_version(profile_id)),
                    sizing,40,receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded',
                    preparation=preparation,**common)
            start=perf_counter();baseline=run(None);baseline_seconds=perf_counter()-start
            start=perf_counter();actual=run(prepared);prepared_seconds=perf_counter()-start
            if actual!=baseline:raise AssertionError('Prepared native execution differs from original full-path execution.')
            row=dict(profile=profile_id,phase=phase,account_paths=args.paths,horizon_calendar_days=3,
                baseline_seconds=baseline_seconds,prepared_seconds=prepared_seconds,
                seconds_per_prepared_path=prepared_seconds/args.paths,
                exact_full_output_parity=True,metrics=actual['metrics'])
            rows.append(row);print(profile_id,phase,round(prepared_seconds,3),'seconds',flush=True)
    result=dict(version='percentage-risk-M0-capacity-v1',synthetic=True,
        conclusion='MAIN_PERCENTAGE_OPTIMIZER_NOT_RELEASED',
        limitations=['Three-session synthetic source and horizon; no representative real-source 1000-path benchmark.',
            'Existing 512-path, 365-day and native bar-work bounds remain enforced.',
            'No 10000-refit two-history OOS estimator is qualified by this benchmark.'],
        source_bars=len(c.bars),source_sessions=len(c.sessions),catalogue_sha256=c.catalogue_sha256,
        preparation_seconds=prep_seconds,preparation_accounted_bytes=prepared.bytes_used,
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        full_experiment_seconds=perf_counter()-started,results=rows,
        source_sha256={str(p):sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),
            Path('alphaquest/prop/native_draws.py'),Path('alphaquest/prop/evaluation_profiles.py'),
            Path('alphaquest/prop/funded_profiles.py')]})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
