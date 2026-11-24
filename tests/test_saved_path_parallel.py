"""Multicore orchestration must preserve ordered paths, cash, seeds and traces."""
from dataclasses import replace
import pytest
from alphaquest.prop.parallel import Runtime,CAPACITY
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,SimulationConfig,EvaluationSamplingConfig,SamplingConfig,SizingTrace,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.evaluation_optimization import SequentialRetry
from test_prop_trade_handling import configured
from test_saved_trade_simulation import metadata


@pytest.mark.parametrize('phase,profile', [('evaluation','lucidflex-50k'),('funded','lucidflex-50k'),('funded','apex-50k-eod')])
@pytest.mark.parametrize('kind,action',[('fixed_contracts','skip'),('percentage_risk','exit_at_limit')])
def test_exact_parallel_paths_traces_and_schedule(phase,profile,kind,action):
    c=configured(kind=kind,action=action,percent='.5',contracts=10)
    days=[[(1100.,50.,(),True,metadata())],[(-250.,250.,(),True,metadata())],[],[(1800.,0.,(),True,metadata())]]
    sim=SimulationConfig(24,42,40);calendar=PhaseCalendar(('2026-11-02','2026-11-09'),'2030-01-01',('2026-11-11',))
    def calculate(trace,progress):
        if phase=='evaluation':
            from alphaquest.prop.evaluation_profiles import calendar_evaluation_paths
            return calendar_evaluation_paths(days,EvaluationProfile(profile,rule_version(profile),'80.50','0'),10,
                sim,EvaluationSamplingConfig(5,24,42),SequentialRetry(max_calendar_days=45),calendar,sizing=c,trace=trace,progress=progress)
        from alphaquest.prop.funded_profiles import _dated_funded_paths
        return _dated_funded_paths(days,FundedProfile(profile,rule_version(profile)),10,45,calendar,2,sim,
            SamplingConfig(5),sizing=c,trace=trace,progress=progress)[:2]
    serial=SizingTrace(c,limit=37);expected=calculate(serial,lambda v:None)
    runtime=Runtime(workers=min(4,CAPACITY));updates=[];trace=SizingTrace(c,limit=37)
    try:
        with runtime.activate():actual=calculate(trace,updates.append)
        assert actual==expected
        assert trace.result()==serial.result()
        assert updates[-1]['completed']==updates[-1]['total']==24
        assert updates[-1]['worker_count']==min(4,CAPACITY)
        assert len(updates[-1]['worker_pids'])>1
        assert runtime.occupied==0
    finally:runtime.close()


def test_job_worker_override_does_not_mutate_runtime_default():
    runtime=Runtime(workers=4)
    try:
        with runtime.activate(workers=2):assert runtime.selected_workers==2
        assert runtime.selected_workers==4
    finally:runtime.close()
