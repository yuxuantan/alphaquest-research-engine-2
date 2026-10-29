"""Default Apex analysis for each new backtest, using the normal local model.

Computation is database-free and spawn-safe. Only the coordinator publishes to
AnalysisStore; failed source checks never fabricate a historical cash value.
"""

from dataclasses import dataclass
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
from uuid import uuid4

from .adapter import canonical
from .native_analysis import DEFAULTS, MODEL_VERSION, prepare, run_analysis
from .store import request_key, seal_report
from ..reporting import json_value


def profiles():
    from .lucid_rules import defaults,MODEL_VERSION as lucid_version
    return [dict(version='automatic-apex50k-eod-native-v4-instrument-commissions',model_version=MODEL_VERSION,
                label='Apex 50K EOD',settings=dict(DEFAULTS),source_mode='native_held_ohlc_bounds'),
            dict(version='automatic-lucidflex50k-eod-v1',model_version=lucid_version,label='LucidFlex 50K',
                settings=defaults(DEFAULTS),source_mode='native_held_ohlc_bounds')]

def profile():
    apex,lucid=profiles()
    return dict(apex,companions=[lucid])


def descriptor():
    apex,lucid=profiles()
    return dict(apex,id=uuid4().hex,companions=[dict(lucid,id=uuid4().hex)])


@dataclass(frozen=True)
class FrozenBacktest:
    root: Path
    record: dict

    def read_source_record(self, id):
        return self.record if id==self.record['id'] else None


def compute_default(root, run_id, manifest, staged, description, progress=lambda message: None, *, runtime=None,calculation_cache=None):
    result=_compute_one(root,run_id,manifest,staged,description,progress,runtime=runtime,calculation_cache=calculation_cache)
    result['companions']=[_compute_one(root,run_id,manifest,Path(staged).parent/('prop-'+item['id']),item,
        lambda message,item=item:progress(item['label']+': '+message),runtime=runtime,calculation_cache=calculation_cache)
        for item in description.get('companions',[])]
    return result

def _compute_one(root, run_id, manifest, staged, description, progress=lambda message: None, *, runtime=None,calculation_cache=None):
    """Return small result metadata; full calculations remain in worker files."""
    created=datetime.now(timezone.utc).isoformat()
    source=FrozenBacktest(Path(root),json.loads(json.dumps(dict(id=run_id,**manifest),default=json_value)))
    request=dict(source_backtest_id=run_id,trade_file='',export_timezone='America/Chicago',settings=description['settings'])
    result=dict(id=description['id'],source_id=run_id,created_at_utc=created,status='incompatible',historical_net=None,
                request_hash='',reason=None)
    # An explicit empty path selects native fills and skips Downloads discovery.
    # This deterministic source choice is also available in the normal form.
    try:
        progress('Checking automatic '+description.get('label','Apex 50K EOD')+' source')
        snapshot,_,settings=prepare(source,run_id,'',description['settings'],'America/Chicago')
        result['request_hash']=request_key(snapshot,settings)
    except (ValueError,KeyError,OSError) as exc:
        result.update(reason=str(exc),request_hash='incompatible:'+description['id'])
        return result
    try:
        staged=Path(staged);staged.mkdir(parents=True)
        from .calculation_cache import use
        with use(calculation_cache),runtime.activate() if runtime else nullcontext():
            report=run_analysis(source,request,staged,progress)
        if report['source']!=snapshot:raise ValueError('Source changed during automatic analysis.')
        seal_report(staged,report,description['id'],created)
        history=report['calculations'].get('history')
        result.update(status='complete',historical_net=history['totals']['net'] if history else None,
                      reason=report['calculations'].get('unavailable'),native_kernel=report['runtime']['native_kernel'],prop_execution=report['runtime']['prop_execution'],calculation_reused_from=report['runtime']['calculation_reused_from'])
    except Exception as exc:
        shutil.rmtree(staged,ignore_errors=True)
        result.update(status='error',reason=f'{type(exc).__name__}: {exc}')
    return result


def publish_backtest(runs, analyses, run_id, output, manifest, prepared=None, prop_directory=None):
    """Index both products, rolling back only this new analysis on save failure."""
    published=[]
    try:
        if prepared:
            for item in [prepared,*prepared.get('companions',[])]:
                directory=prop_directory if item is prepared else Path(prop_directory).parent/('prop-'+item['id'])
                analyses.publish_prepared(item,directory);published.append(item)
        return runs.complete(run_id,output,manifest)
    except BaseException:
        for item in reversed(published):analyses.discard_prepared(item)
        raise
