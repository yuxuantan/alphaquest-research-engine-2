"""Durable continuations on the existing AnalysisStore worker and parent record.

No page polling, new service, account engine or duplicate report store. Completion
notifications queue only short orchestration tasks; numerical jobs remain owned
by their normal phase workers. Older simulations have no automatic plan.
"""
from datetime import datetime,timezone
import json
from types import SimpleNamespace
from uuid import uuid4

from .prop_sim_selection import identity,choose

PHASES=('evaluation','funded')
TERMINAL={'complete','no_eligible_candidates','error','cancelled'}


def initial_state():
    return dict(version='prop-sim-automatic-v1',selection_identity=identity(),stop_requested=False,
        phases={p:dict(stage='is_running') for p in PHASES})


class PropSimAutomation:
    def __init__(self,app):
        self.app=app;self.analyses=app.state.prop_analyses
        self.request=SimpleNamespace(app=app);self.closed=False;self.pending=set()

    def _read(self,id):
        with self.analyses.connect() as db:
            row=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
        return json.loads(row[0]) if row else None

    def _write(self,saved):
        saved['automation']['updated_at_utc']=datetime.now(timezone.utc).isoformat()
        with self.analyses.connect() as db:
            db.execute('UPDATE workflow_prop_simulations SET payload=? WHERE id=?',(json.dumps(saved),saved['id']))

    def schedule(self,id):
        with self.analyses.lock:
            if self.closed or id in self.pending:return
            saved=self._read(id)
            if not saved or not saved.get('automation') or saved['automation']['stop_requested']:return
            self.pending.add(id)
            try:self.analyses.worker.submit(self._advance,id)
            except RuntimeError:self.pending.discard(id)

    def analysis_finished(self,analysis_id):
        if self.closed:return
        with self.analyses.connect() as db:
            ids=[r[0] for r in db.execute('SELECT DISTINCT p.simulation_id FROM workflow_prop_sim_phases p '
                'JOIN campaign_analyses a ON a.campaign_id=p.campaign_id WHERE a.analysis_id=?',(analysis_id,))]
        for id in ids:self.schedule(id)

    def recover(self):
        with self.analyses.connect() as db:
            ids=[r[0] for r in db.execute("SELECT id FROM workflow_prop_simulations WHERE json_extract(payload,'$.automation.version')='prop-sim-automatic-v1'")]
        for id in ids:self.schedule(id)

    def resume(self,id):
        with self.analyses.lock:
            saved=self._read(id)
            if not saved or not saved.get('automation'):return
            saved['automation']['stop_requested']=False
            for state in saved['automation']['phases'].values():
                if state['stage'] in ('error','cancelled'):
                    state['stage']='is_running';state['explicit_retry']=True;state.pop('error',None)
            self._write(saved);self.schedule(id)

    def stop(self,id):
        with self.analyses.lock:
            saved=self._read(id)
            if not saved or not saved.get('automation'):return
            saved['automation']['stop_requested']=True
            for state in saved['automation']['phases'].values():
                if state['stage'] not in TERMINAL:state['stage']='cancelled'
            self._write(saved)  # Persist intent before issuing any job cancellations.
            retained=[]
            for cid in saved['campaign_ids'].values():
                campaign=self.app.state.campaigns.get(cid)
                jobs=[campaign.get('analysis')]+[a.get('analysis') for a in self.app.state.campaigns.assessments(cid)]
                for job in jobs:
                    if job and job['status'] in ('queued','running'):
                        with self.analyses.connect() as db:
                            shared=db.execute('SELECT 1 FROM campaign_analyses WHERE analysis_id=? AND campaign_id NOT IN (?,?) LIMIT 1',
                                (job['id'],*saved['campaign_ids'].values())).fetchone()
                        if shared:retained.append(job['id'])
                        else:self.analyses.cancel_phase(job['id'])
            saved['automation']['retained_shared_analysis_ids']=retained
            self._write(saved)

    @staticmethod
    def _interrupted(job):
        return job and job['status']=='error' and job.get('progress')=='Interrupted'

    def _phase(self,saved,phase):
        from .prop_sim import qualified,Selection,FrozenAssessment,submit_assessment
        from .research_campaigns import FreezeRequest
        store=self.app.state.campaigns;cid=saved['campaign_ids'][phase]
        state=saved['automation']['phases'][phase]
        if state['stage'] in TERMINAL:return
        campaign=store.get(cid);job=campaign.get('analysis')
        if not job or self._interrupted(job) or state.get('explicit_retry') and job['status'] in ('error','cancelled'):
            qualified(self.request,Selection.model_validate(saved['configuration']['selections'][0]))
            store.run(cid);state['stage']='is_running';self._write(saved);return
        if job['status'] in ('queued','running'):
            state['stage']='is_running';return
        if job['status']!='complete':
            state.update(stage='cancelled' if job['status']=='cancelled' else 'error',error=job.get('error'));self._write(saved);return
        if saved['automation']['selection_identity']!=identity():
            raise ValueError('Automatic selection implementation changed; preserve this run and create a new simulation.')
        if not state.get('selection'):
            # This reads only the original IS report. No OOS report is consulted.
            report=store.report(cid);selection=choose(report,phase)
            selection.update(is_analysis_id=report['id'],is_report_sha256=self.analyses.fingerprint(report['id'])['files']['report.json'])
            state['selection']=selection;self._write(saved)
        selection=state['selection']
        if selection['status']!='selected':
            state['stage']='no_eligible_candidates';self._write(saved);return
        names={}
        for c in selection['candidates']:
            name=(c.get('sizing_label') or f"{c['micros']} MNQ")+' · '+' / '.join(c['roles'])
            # The full sizing policy and roles remain in the frozen rationale.
            names[c['candidate_id']]=name if len(name)<=120 else name[:119].rstrip()+'…'
        # Freeze is idempotent and immutable, including recovery between writes.
        frozen=store.freeze(cid,FreezeRequest(candidate_ids=list(names),names=names,
            rationale='Automatically selected from IS only. '+json.dumps(dict(policy=selection['selection_identity'],
                selection_sha256=selection['selection_sha256'],roles=selection['candidates']),separators=(',',':'))))
        state['frozen_package_sha256']=frozen['package_sha256']
        attempt=next((a for a in store.assessments(cid) if a['request_id']==state.get('oos_request_id')),None)
        if attempt and attempt['status'] in ('error','cancelled'):
            interrupted_launch=not attempt.get('analysis_id') and str(attempt.get('error','')).startswith('Application stopped during OOS launch')
            if self._interrupted(attempt.get('analysis')) or interrupted_launch or state.pop('explicit_retry',False):
                state.pop('oos_request_id',None);attempt=None
            else:
                state.update(stage='cancelled' if attempt['status']=='cancelled' else 'error',error=(attempt.get('analysis') or {}).get('error') or attempt.get('error'));self._write(saved);return
        if not attempt:
            state.setdefault('oos_request_id',uuid4().hex);state['stage']='oos_running';self._write(saved)
            attempt=submit_assessment(self.request,saved['id'],phase,FrozenAssessment(request_id=state['oos_request_id'],kind='qualification'))
            state['oos_request_id']=attempt['request_id']
        state['oos_analysis_id']=attempt.get('analysis_id')
        state['stage']='complete' if attempt['status']=='complete' else 'oos_running'
        state.pop('explicit_retry',None)
        self._write(saved)

    def _advance(self,id):
        with self.analyses.lock:
            # Clear before launching children so cached/instant completion cannot
            # lose the next notification. This worker serializes continuations.
            self.pending.discard(id)
            if self.closed:return
            saved=self._read(id)
            if not saved or not saved.get('automation') or saved['automation']['stop_requested']:return
            for phase in PHASES:
                try:self._phase(saved,phase)
                except Exception as exc:
                    saved['automation']['phases'][phase].update(stage='error',error=f'{type(exc).__name__}: {exc}')
                    self._write(saved)

    def close(self):
        with self.analyses.lock:self.closed=True
