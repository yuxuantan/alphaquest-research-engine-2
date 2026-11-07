"""Complete-procedure applications in the existing research/AnalysisStore owners.

This layer only orchestrates existing qualification, phase search and replay.
Saved campaign reports remain immutable; each terminal application is a normal
AnalysisStore report with its own immutable source, selection and access journal.
"""
from contextvars import ContextVar
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .optimization_cache import engine_identity
from .prop.adapter import canonical
from .prop.store import seal_report, sealed_checks
from .research import ResearchConflict
from .research_access import ReservationRequest, final_authorization, source_identity
from .research_folds import FoldSettings, inventory_sessions
from .research_procedure import (TerminalSelection, FinalEvidenceRules, terminal_plan,
    freeze_procedure, verify_procedure, recommendation_phase, assess_final_outcomes, digest)

_active_application=ContextVar('research_procedure_application',default=None)


class ProcedureStore:
    def _init_procedures(self):
        with self.analyses.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS research_procedures (
                    id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL UNIQUE,sha256 TEXT NOT NULL UNIQUE,
                    preview_sha256 TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_procedure_applications (
                    id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL,procedure_sha256 TEXT NOT NULL,
                    purpose TEXT NOT NULL,declaration TEXT NOT NULL,analysis_id TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0);
            ''')

    def _procedure_status(self,id):
        with self.analyses.connect() as db:
            row=db.execute('SELECT payload FROM research_procedures WHERE campaign_id=?',(id,)).fetchone()
            applications=db.execute('SELECT id FROM research_procedure_applications WHERE campaign_id=? ORDER BY rowid',(id,)).fetchall()
        return dict(procedure=self._procedure(id) if row else None,
            applications=[self.application(id,app_id) for app_id, in applications])

    def application(self,id,application_id):
        with self.analyses.connect() as db:
            row=db.execute('SELECT purpose,declaration,analysis_id,cancel_requested,procedure_sha256 FROM research_procedure_applications WHERE id=? AND campaign_id=?',(application_id,id)).fetchone()
        if not row:raise KeyError('Procedure application not found.')
        analysis=self.analyses.get(row[2]) if row[2] else None
        value=dict(application_id=application_id,purpose=row[0],declaration=json.loads(row[1]),analysis_id=row[2],
            cancel_requested=bool(row[3]),procedure_sha256=row[4],status=analysis['status'] if analysis else 'validated',
            progress=analysis['progress'] if analysis else 'Application saved.',error=analysis['error'] if analysis else None)
        if value['status']=='complete':value['result']=self.application_report(id,application_id)['calculations']
        return value

    def application_report(self,id,application_id):
        with self.analyses.connect() as db:
            row=db.execute('SELECT analysis_id FROM research_procedure_applications WHERE id=? AND campaign_id=?',(application_id,id)).fetchone()
        if not row or not row[0] or self.analyses.get(row[0])['status']!='complete':
            raise ResearchConflict('Procedure application has no completed report.')
        if not self.analyses.fingerprint(row[0]):raise ResearchConflict('Saved procedure application artifacts changed.')
        return json.loads((self.analyses.root/row[0]/'report.json').read_text())

    def _procedure(self,id,sha=None,*,calculate=False):
        with self.analyses.connect() as db:
            row=db.execute('SELECT sha256,payload FROM research_procedures WHERE campaign_id=?',(id,)).fetchone()
        if not row:raise ResearchConflict('Freeze the complete research procedure first.')
        if sha is not None and sha!=row[0]:raise ResearchConflict('Requested procedure differs from the authoritative freeze.')
        try:return verify_procedure(json.loads(row[1]),authoritative_sha256=row[0],
            current_engine_identity=engine_identity() if calculate else None)
        except ValueError as exc:raise ResearchConflict(str(exc)) from exc

    def _snapshot(self,plan,snapshot_id):
        dataset=self.datasets.get(snapshot_id or plan['dataset']['id'])
        if dataset is None:raise KeyError('Source snapshot is unavailable.')
        if any(dataset.get(key)!=value for key,value in plan['instrument'].items()):
            raise ResearchConflict('Snapshot instrument identity changed from the evaluated procedure.')
        original=self.datasets.get(plan['dataset']['id'])
        if original is None:raise ResearchConflict('Original development source is unavailable.')
        if (dataset.get('instrument_settings')!=original.get('instrument_settings') or dataset.get('symbol')!=original.get('symbol')
                or dataset['source_timezone']!=original['source_timezone']):
            raise ResearchConflict('Snapshot instrument or timestamp interpretation differs from development.')
        inventory=inventory_sessions(self.datasets,dataset['id'])
        development=plan['session_inventory'];sessions=development['sessions']
        for day in sessions:
            if (inventory['session_content_sha256'].get(day)!=development['session_content_sha256'].get(day)
                    or inventory['counts'].get(day)!=development['counts'].get(day)):
                raise ResearchConflict('Snapshot changed or omitted frozen development observations.')
        identity=dict(dataset={key:dataset[key] for key in plan['dataset']},instrument=deepcopy(plan['instrument']),
            sessions=list(sessions),session_content_sha256={day:inventory['session_content_sha256'][day] for day in sessions},
            counts={day:inventory['counts'][day] for day in sessions},source=source_identity(dataset))
        # The canonical content identity is per session; exact raw bytes and the
        # selected dataset snapshot are retained as independent provenance.
        identity['content_sha256']=digest({key:identity[key] for key in ('sessions','session_content_sha256','counts')})
        return dataset,inventory,identity

    def _target_sessions(self,plan,settings):
        start=date.fromisoformat(plan['session_inventory']['sessions'][-1])+timedelta(days=1)
        calendars=[]
        for study in plan['economic_studies']:
            calendar=study['search_settings']['calendar'];closures=set(calendar.get('closures',[]));days=[];cursor=start
            while len(days)<settings.outer_test_sessions:
                if cursor.weekday()<5 and cursor.isoformat() not in closures:days.append(cursor.isoformat())
                cursor+=timedelta(days=1)
                if (cursor-start).days>3660:raise ValueError('Terminal forecast calendar has insufficient declared open sessions.')
            calendars.append(days)
        if not calendars or any(value!=calendars[0] for value in calendars):
            raise ValueError('Independent phase calendars must agree on the terminal assessment session window.')
        return calendars[0]

    def procedure_preview(self,id,body):
        campaign=self.get(id)
        if campaign['status']!='complete':raise ResearchConflict('Complete the declared nested evaluation before freezing its procedure.')
        self.check(id);self._verify_steps(id);plan=campaign['plan'];declaration=campaign['declaration']
        if 'terminal_selection' not in declaration or 'final_evidence' not in declaration:
            raise ResearchConflict('Historical campaign did not predeclare the terminal procedure; create and evaluate a new declaration.')
        terminal=TerminalSelection.model_validate(declaration['terminal_selection'])
        rules=FinalEvidenceRules.model_validate(declaration['final_evidence'])
        if not plan.get('economic_studies'):raise ValueError('Complete procedure selection requires independent economic studies.')
        dataset,inventory,development=self._snapshot(plan,body.get('source_snapshot_id'))
        settings=FoldSettings.model_validate(declaration['folds']);target=self._target_sessions(plan,settings)
        window=terminal_plan(development['sessions'],target,settings,origin_session=development['sessions'][0])
        reservation_id=body.get('reservation_id');access=dict(status='NOT_REQUESTED',untouched_certificate=False)
        if reservation_id:
            guard=self.datasets.research_access;reservation=guard.get(reservation_id)
            if reservation['sessions']!=target:raise ValueError('Reserved final sessions must exactly match the predeclared next assessment window.')
            if reservation['status'] not in ('RESERVED','BOUND'):raise ResearchConflict('Final reservation has been released or consumed.')
            reservation_request=ReservationRequest.model_validate({k:v for k,v in reservation['declaration'].items() if k!='dataset_id'})
            checked=guard.preview(self.datasets,dataset['id'],reservation_request);access=checked['access']
            if checked['proposed_sessions']!=target:raise ValueError('Final snapshot does not contain the exact reserved session window.')
        economic=self._economic_preview([__import__('alphaquest.research_phase_selection',fromlist=['PhaseStudy']).PhaseStudy.model_validate(s) for s in plan['economic_studies']],
            plan['candidates'],[window],
            [__import__('alphaquest.research_phase_selection',fromlist=['BaselineDeclaration']).BaselineDeclaration.model_validate(b) for b in plan['baselines']],inventory)
        value=dict(version='procedure-preview-v1',campaign_id=id,development=development,terminal_plan=window,
            terminal_selection=terminal.model_dump(mode='json'),final_evidence=rules.model_dump(mode='json'),
            reservation_id=reservation_id,access=access,evaluated_report=self.analyses.fingerprint(campaign['analysis_id']),
            economic_plan=economic,source_snapshot_id=dataset['id'],complete_configuration_count=len(plan['candidates']),
            target_calendar_provenance='User-declared modeled weekdays and closures; not verified future market observations.',
            current_development_available=True,final_verification_available=bool(reservation_id and access['status']=='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE'),
            interpretation='A fresh complete terminal fit on pinned development; no last-fold promotion or holdout-driven reselection.')
        value['preview_sha256']=digest(value)
        return value

    def procedure_freeze(self,id,body):
        with self.analyses.lock:
            with self.analyses.connect() as db:existing=db.execute('SELECT preview_sha256,payload FROM research_procedures WHERE campaign_id=?',(id,)).fetchone()
            if existing:
                saved=json.loads(existing[1])
                if saved['procedure_id']!=body['procedure_id'] or existing[0]!=body['expected_preview_sha256']:
                    raise ResearchConflict('This evaluated campaign already has its immutable procedure freeze.')
                return self._procedure(id)
            preview=self.procedure_preview(id,body)
            if preview['preview_sha256']!=body['expected_preview_sha256']:raise ResearchConflict('Procedure preview changed; review the current concrete declaration.')
            campaign=self.get(id)
            package=freeze_procedure(campaign,terminal=TerminalSelection.model_validate(preview['terminal_selection']),
                evidence_rules=FinalEvidenceRules.model_validate(preview['final_evidence']),terminal_window=preview['terminal_plan'],
                report_fingerprint=preview['evaluated_report'],development_identity=preview['development'],access_evidence=preview['access'],
                reservation_id=preview['reservation_id'],procedure_id=body['procedure_id'],created_at_utc=datetime.now(timezone.utc).isoformat())
            with self.analyses.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if package['reservation_id']:self.datasets.research_access.bind(package['reservation_id'],package['procedure_sha256'],db=db)
                db.execute('INSERT INTO research_procedures VALUES (?,?,?,?,?)',(body['procedure_id'],id,package['procedure_sha256'],preview['preview_sha256'],canonical(package)))
            return package

    def final_preview(self,id,body):
        package=self._procedure(id,body['procedure_sha256'],calculate=True)
        if not package['reservation_id'] or body['reservation_id']!=package['reservation_id']:
            raise ResearchConflict('Final assessment must use its frozen reservation.')
        if body['source_snapshot_id']!=package['development']['dataset']['id']:
            raise ResearchConflict('Final assessment cannot replace its frozen source snapshot.')
        campaign=self.get(id);dataset,inventory,development=self._snapshot(campaign['plan'],body['source_snapshot_id'])
        if development!=package['development']:raise ResearchConflict('Frozen development/source snapshot changed.')
        guard=self.datasets.research_access;reservation=guard.get(body['reservation_id'])
        request=ReservationRequest.model_validate({k:v for k,v in reservation['declaration'].items() if k!='dataset_id'})
        access=guard.preview(self.datasets,dataset['id'],request)['access']
        if reservation['status']=='CONSUMED':access=dict(access,status='ALREADY_CONSUMED',application_id=reservation['application_id'])
        value=dict(procedure_sha256=package['procedure_sha256'],reservation_id=reservation['id'],source_snapshot_id=dataset['id'],
            terminal_plan=package['terminal_plan'],access=access,
            available=reservation['status']=='BOUND' and access['status']=='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE')
        value['preview_sha256']=digest(value);return value

    def run_application(self,id,body,purpose):
        package=self._procedure(id,body['procedure_sha256'],calculate=True);app_id=body['request_id']
        declaration=dict(body,purpose=purpose)
        with self.analyses.lock:
            with self.analyses.connect() as db:previous=db.execute('SELECT declaration FROM research_procedure_applications WHERE id=?',(app_id,)).fetchone()
            if previous:
                if json.loads(previous[0])!=declaration:raise ResearchConflict('Application request ID already binds a different action.')
                saved=self.application(id,app_id)
                if saved['status'] in ('queued','running','complete'):return saved
            elif purpose=='final_verification':
                preview=self.final_preview(id,body)
                if not preview['available']:raise ResearchConflict('Final data is not eligible: '+preview['access']['status'])
                if body['expected_preview_sha256']!=preview['preview_sha256']:raise ResearchConflict('Final access preview changed; review it again.')
            elif purpose!='current_development':raise ValueError('Unknown procedure application purpose.')
            analysis_id=uuid4().hex;created=datetime.now(timezone.utc).isoformat()
            with self.analyses.connect() as db:
                if db.execute("SELECT count(*) FROM analyses WHERE status IN ('queued','running')").fetchone()[0]>=8:
                    raise ResearchConflict('Analysis queue is full.')
                if not previous:db.execute('INSERT INTO research_procedure_applications VALUES (?,?,?,?,?,NULL,0)',(app_id,id,package['procedure_sha256'],purpose,canonical(declaration)))
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,NULL)',(analysis_id,digest(declaration),package['original_declaration']['source_backtest_id'],created,'queued','Queued complete terminal procedure'))
                db.execute('UPDATE research_procedure_applications SET analysis_id=?,cancel_requested=0 WHERE id=?',(analysis_id,app_id))
                db.execute('INSERT INTO campaign_analyses VALUES (?,?)',(id,analysis_id))
                db.execute('INSERT INTO analysis_sources SELECT ?,source_id FROM campaign_sources WHERE campaign_id=?',(analysis_id,id))
            self.analyses.worker.submit(self._run_application,id,app_id,analysis_id)
            return self.application(id,app_id)

    def cancel_application(self,id,app_id):
        with self.analyses.lock:
            value=self.application(id,app_id)
            if value['status'] not in ('queued','running'):raise ResearchConflict('Only queued or running applications can be cancelled.')
            with self.analyses.connect() as db:db.execute('UPDATE research_procedure_applications SET cancel_requested=1 WHERE id=?',(app_id,))
            return self.application(id,app_id)

    def _application_checkpoint(self):
        app_id=_active_application.get()
        if app_id:
            with self.analyses.connect() as db:value=db.execute('SELECT cancel_requested FROM research_procedure_applications WHERE id=?',(app_id,)).fetchone()
            if value and value[0]:raise ResearchConflict('Cancelled at a durable procedure checkpoint. Resume the same application to reuse verified completed work.')

    def _run_application(self,id,app_id,analysis_id):
        token=_active_application.set(app_id)
        try:
            application=self.application(id,app_id);purpose=application['purpose']
            package=self._procedure(id,application['procedure_sha256'],calculate=True)
            self._verify_steps(id)
            campaign=deepcopy(self.get(id));plan=campaign['plan'];dataset,inventory,development=self._snapshot(plan,package['development']['dataset']['id'])
            if development!=package['development']:raise ResearchConflict('Pinned procedure development source changed.')
            if self.analyses.fingerprint(campaign['analysis_id'])!=package['evaluated_report']:raise ResearchConflict('Evaluated research artifacts changed after procedure freeze.')
            plan['dataset']=deepcopy(development['dataset'])
            plan['session_inventory']=dict(inventory,sessions=development['sessions'],**{key:{day:inventory[key][day] for day in development['sessions']} for key in ('counts','bounds','session_content_sha256')})
            window=dict(deepcopy(package['terminal_plan']),application_id=app_id,procedure_sha256=package['procedure_sha256'],
                application_role='final_fit' if purpose=='final_verification' else 'current_development')
            self.analyses._update(analysis_id,'running','Rerunning the complete terminal qualification and independent phase search')
            qualification,evidence,backtests,regimes=self._qualify_window(campaign,analysis_id,window)
            selection=self._select_economic(campaign,analysis_id,window,qualification)
            references=self._prepare_baselines(campaign,analysis_id,window,qualification)
            self._checkpoint(id);replay=None;baseline_results=[];access=None;assessment=None;final_status='NOT_REQUESTED'
            if purpose=='final_verification':
                packages=[p for phase in selection['phases'] for p in phase['frozen_packages']]
                packages += [r['frozen_package'] for r in (references or {}).get('baseline_results',[])]
                if packages:
                    access=self.datasets.research_access.authorize_final(package['reservation_id'],procedure_sha256=package['procedure_sha256'],
                        application_id=app_id,selection_seal_sha256=selection['selection_seal_sha256'],source=source_identity(dataset),
                        allowed_package_sha256=[p['package_sha256'] for p in packages])
                    with final_authorization(access['token_id']):
                        replay=self._replay_economic(campaign,analysis_id,window,selection,references)
                        baseline_results=self._replay_baselines(campaign,analysis_id,window,selection,references)
                    assessment=assess_final_outcomes(replay,FinalEvidenceRules.model_validate(package['algorithm']['final_evidence']))
                    final_status=assessment['status']
                else:final_status='NOT_ASSESSED_NO_SELECTED_POLICY'
            else:
                reservation=(self.datasets.research_access.get(package['reservation_id']) if package.get('reservation_id') else None)
                if reservation and reservation['status']=='CONSUMED':
                    # Access is permanent even when cancellation/failure prevented
                    # a completed report. An optional final cannot erase it.
                    final_status='INCOMPLETE_REPLAY'
                    prior=self.application(id,reservation['application_id'])
                    if prior['status']=='complete':final_status=prior['result']['final_verification']['status']
                else:
                    with self.analyses.connect() as db:
                        finals=db.execute("SELECT id FROM research_procedure_applications WHERE campaign_id=? AND purpose='final_verification' ORDER BY rowid DESC",(id,)).fetchall()
                    if finals:
                        prior=self.application(id,finals[0][0])
                        final_status=(prior['result']['final_verification']['status'] if prior['status']=='complete' else 'FINAL_SELECTION_PENDING_OR_INTERRUPTED_BEFORE_ACCESS')
            base_report=self.report(id);reliability=base_report['calculations']['reliability']
            recommendations=[]
            for phase in selection['phases']:
                blockers=(phase.get('deployment_readiness') or {}).get('reasons',[])
                recommendations.append(dict(phase=phase['phase'],**recommendation_phase(current_selection=phase,qualification=qualification,
                    reliability_status=(reliability.get('phases',{}).get(phase['phase']) or {}).get('status',reliability['status']),
                    final_status=final_status,rules=FinalEvidenceRules.model_validate(package['algorithm']['final_evidence']),
                    model_blockers=blockers,operational_blockers=['Live execution and provider authorization are not qualified by this research application.'])))
            declared_phases={s['phase'] for s in plan['economic_studies']}
            for missing in sorted(declared_phases-{r['phase'] for r in recommendations}):
                recommendations.append(dict(phase=missing,status='NO_QUALIFIED_DEPLOYMENT_CANDIDATE',selected_packages=[],production_qualified=False,
                    evidence_blockers=[selection['status']],no_reselection=True))
            self._checkpoint(id);self._procedure(id,package['procedure_sha256'],calculate=True);self._verify_steps(id)
            result=dict(campaign_id=id,source_backtest_id=package['original_declaration']['source_backtest_id'],application_id=app_id,purpose=purpose,procedure_sha256=package['procedure_sha256'],terminal_plan=window,
                qualification=qualification,inner_evidence=evidence,backtests=backtests,regime_evidence=regimes,
                economic_selection=selection,baseline_results=baseline_results,baseline_freeze=references,
                final_verification=dict(status=final_status,replay=replay,access=access,assessment=assessment,selection_repeated_on_final=False),
                recommendation=recommendations,selection_reliability=reliability,event_journal=self._journal(id),
                readiness=dict(production_qualified=False,status='RESEARCH_ONLY'),
                interpretation='Complete procedure applied to pinned eligible development; final data excluded from qualification and policy selection. Families retain every selected member without implicit weighting.')
            with TemporaryDirectory(prefix='.pending-',dir=self.analyses.root) as temporary:
                staged=Path(temporary)/'report';staged.mkdir()
                files={'procedure.json':package,'terminal_plan.json':window,'qualification.json':qualification,'economic_selection.json':selection,
                    'baseline_results.json':baseline_results,'final_verification.json':result['final_verification'],'recommendation.json':recommendations,
                    'research_journal.json':result['event_journal'],'access_evidence.json':access,'calculations.json':result}
                for name,value in files.items():(staged/name).write_text(canonical(value))
                report=dict(format_version=6,phase='research_integrity',model_version='procedure-application-v1',
                    settings=dict(ANALYSIS_MODE='nested_research'),request=application['declaration'],plan=window,
                    calculations=result,implementation=dict(engine_identity=plan['engine_identity']))
                seal_report(staged,report,analysis_id,self.analyses.get(analysis_id)['created'])
                checks=sealed_checks(staged)
                # Cancellation and publication share one lock. A request accepted
                # while archives were staged must win before rename/status commit.
                with self.analyses.lock,self.analyses.connect() as db:
                    self._checkpoint(id)
                    self._procedure(id,package['procedure_sha256'],calculate=True)
                    staged.rename(self.analyses.root/analysis_id)
                    db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(analysis_id,canonical(checks)))
                    db.execute("UPDATE analyses SET status='complete',progress=? WHERE id=?",('Complete procedure application saved; no live qualification',analysis_id))
        except Exception as exc:
            self.analyses._update(analysis_id,'error','Procedure application stopped; completed checkpoints retained',f'{type(exc).__name__}: {exc}')
        finally:_active_application.reset(token)
