import sys,os,json
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,os.getcwd())
from alphaquest.prop.evaluation_profiles import calendar_evaluation_paths
from alphaquest.prop.evaluation_optimization import SequentialRetry,acquisition_metrics
from alphaquest.prop.phase_profiles import EvaluationProfile,SimulationConfig,EvaluationSamplingConfig,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from types import SimpleNamespace
out=[]
books=[[[ (1000.,0.)]],[[(-1500.,1500.),(2000.,0.)]],[[]],[[(4000.,0.)],[],[(1000.,0.)],[(-1300.,1400.)]]]
for profile in ('apex-50k-eod','lucidflex-50k'):
 for chronology in (False,True):
  if profile=='apex-50k-eod' and not chronology:continue
  for dll in (False,True):
   p=EvaluationProfile(profile,rule_version(profile),'80.50','129',dll)
   for book in books:
    for guard,delay,attempts in ((5,0,1),(12,2,4),(40,0,3)):
     r=calendar_evaluation_paths(book*30 if chronology else book,p,10,SimulationConfig(8,42,40),EvaluationSamplingConfig(5,8,42),SequentialRetry(activation_delay_sessions=delay,max_calendar_days=guard,max_attempts=attempts),PhaseCalendar(('2026-11-13','2026-11-14'),'2027-01-31',('2026-11-26',)),chronological=chronology)
     out.append(r)
# Renewals: failures, long streams beyond the prefix, exact guard/readiness.
p=EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'49','129')
for outcomes,durations in ((['passed','blown','timeout'],[2,1,21]),(['blown']*99+['passed'],[1]*100)):
 for guard,delay in ((5,0),(60,2),(3650,0)):
  c=SimpleNamespace(outcomes=outcomes,duration_weekdays=durations,censoring=SimpleNamespace(censored_paths=0))
  out.append(acquisition_metrics(c,p,SequentialRetry(max_calendar_days=guard,activation_delay_sessions=delay),PhaseCalendar(('2026-11-13','2026-11-14'),'2037-01-31',('2026-11-26',)),EvaluationSamplingConfig(5,16,42)))
Path(sys.argv[1]).write_text(json.dumps(out,sort_keys=True));print(len(out),'full capture cases')
