"""Read-only source benchmark; writes evidence only to the chosen output path."""
import sys,os,json,pickle,sqlite3
from pathlib import Path
from dataclasses import replace
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from time import perf_counter
from hashlib import sha256
sys.path.insert(0,os.getcwd())
import numpy as np
from alphaquest.prop.phase_profiles import SavedTradeSource,ResearchPeriod,prepare_phase_source
from alphaquest.prop.oos_qualification import _book_classes,RULES,definitions
from alphaquest.prop.oos_bootstrap import _replicate
ROOT=Path(os.environ.get('ALPHAQUEST_REFIT_SOURCE_ROOT','/Users/yx/alphaquest-research-engine-2'))
class Runs:
 root=ROOT/'data/backtest_runs'
 @contextmanager
 def connect(self):
  db=sqlite3.connect(f'file:{ROOT}/data/backtests.sqlite3?mode=ro',uri=True)
  try:yield db
  finally:db.close()
 def read_source_record(self,id):
  with self.connect() as db:r=db.execute('SELECT manifest FROM runs WHERE id=?',(id,)).fetchone()
  return json.loads(r[0]) if r else None
 get=read_source_record

def load(profile,phase,size):
 from alphaquest.prop.phase_dispatch import module_for_mode
 ids={('apex','evaluation'):'a11f6078cef3415c96ac0c8f1d423921',('apex','funded'):'609ec63f9b2f4af2ad84c40d920eb484',('lucid','evaluation'):'203112a3eedc47ca80d4e7dc082c655f',('lucid','funded'):'a2309011784440f7acfbd6b70afb5b4e'}
 r=json.loads((ROOT/'data/prop_analyses'/ids[profile,phase]/'report.json').read_text())
 search=module_for_mode(phase+'_optimization').parse_request(r['request'])
 c=next(c for c in search.candidates if c.micros==size)
 if profile=='apex':
  row=next(r for r in r['calculations']['candidates'] if r['configuration']['micros']==size)
  binding=next(b for b in r['assessment']['sources'] if b['frozen_candidate_id']==row['frozen_candidate_id'])
  original=binding['frozen_manifest']['configuration']
  candidates=(replace(c,source=SavedTradeSource(**original['source']),period=ResearchPeriod(**original['period'])),c)
 else:candidates=(c,replace(c,source=SavedTradeSource('8550eb299e0446d9b71376a80ff853a6'),period=ResearchPeriod('2025-01-02','2026-07-07')))
 books=[]
 for candidate in candidates:
  _,days,_=prepare_phase_source(Runs(),candidate.source,candidate.profile,candidate.micros,candidate.simulation,candidate.period,candidate.costs,candidate.sizing);books.append(days)
 return search,candidates,books

def evaluate(profile,phase,size):
 search,candidates,books=load(profile,phase,size)
 with TemporaryDirectory(prefix='aq-exact-refits-') as temp:
  path=Path(temp)/'context.pkl'
  raw=pickle.dumps(dict(books=books,candidates=candidates,search=search,codes=tuple(_book_classes(b) for b in books),cancel_file=str(Path(temp)/'stop'),history_seed=RULES['history_seed'],outer_block=5,maximum_inner_relative_standard_error=.05,metrics=[k for k,_,_,_ in definitions(phase)]),protocol=pickle.HIGHEST_PROTOCOL)
  path.write_bytes(raw);prefix=str(path),sha256(raw).hexdigest()
  rows=[];timings=[]
  for i in (0,1,2,17):
   start=perf_counter();v=_replicate((*prefix,i));timings.append(perf_counter()-start);rows.append(v['replicate'])
  return dict(profile=profile,phase=phase,size=size,inner_paths=candidates[0].simulation.simulations,seconds=timings,replicates=rows)
if __name__=='__main__':
 out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True)
 cases=[('apex','evaluation',27),('apex','funded',13),('lucid','evaluation',3),('lucid','evaluation',21),('lucid','funded',21)]
 results=[]
 for case in cases:
  r=evaluate(*case);results.append(r);out.write_text(json.dumps(results,indent=2));print(case,r['seconds'],flush=True)
