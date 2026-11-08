"""forward observations in the existing AnalysisStore, never a new DB."""
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from alphaquest.prop.store import seal_report, sealed_checks
from .forward_contracts import MonitorDeclaration, EventBatch, Assessment, Control, utc
from .forward_reconcile import canonical, digest, effective_records, reconcile, stamp
from .forward_comparison import check_observation_plan, compare_observation


class Conflict(ValueError):
    """Immutable request identity or advisory recovery conflict."""


def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def implementation_identity():
    root=Path(__file__).parent
    return digest({name:sha256((root/name).read_bytes()).hexdigest()
                   for name in ('forward_contracts.py','forward_reconcile.py','forward_monitoring.py','forward_policy.py','forward_access.py','forward_comparison.py','forward_conformance.py','prop/sizing.py')})


def parse_batch(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=4*1024*1024:
        raise ValueError('Event batches require 1 byte to 4 MiB of UTF-8 JSON.')
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('Duplicate JSON field: '+key)
            value[key]=item
        return value
    def constant(value):raise ValueError('Non-finite JSON constants are unsupported.')
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=constant)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise ValueError('Expected a UTF-8 JSON event envelope.') from exc
    return EventBatch.model_validate(value)


class ForwardStore:
    def __init__(self,analyses,*,resolve_policy=None,record_exposure=None,clock=now,identity=implementation_identity):
        self.analyses=analyses;self.resolve_policy=resolve_policy;self.record_exposure=record_exposure
        self.clock=clock;self.identity=identity
        with analyses.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS forward_monitors (
                    id TEXT PRIMARY KEY,declaration TEXT NOT NULL,policy TEXT NOT NULL,
                    created TEXT NOT NULL,pause_latched INTEGER NOT NULL DEFAULT 0,retired INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS forward_event_batches (
                    monitor_id TEXT NOT NULL,batch_id TEXT NOT NULL,raw_sha256 TEXT NOT NULL,
                    canonical_sha256 TEXT NOT NULL,raw BLOB NOT NULL,filename TEXT NOT NULL,
                    received TEXT NOT NULL,PRIMARY KEY(monitor_id,batch_id));
                CREATE TABLE IF NOT EXISTS forward_events (
                    monitor_id TEXT NOT NULL,sequence INTEGER NOT NULL,event_id TEXT NOT NULL,
                    payload TEXT NOT NULL,received TEXT NOT NULL,batch_id TEXT NOT NULL,
                    PRIMARY KEY(monitor_id,sequence),UNIQUE(monitor_id,event_id));
                CREATE TABLE IF NOT EXISTS forward_controls (
                    monitor_id TEXT NOT NULL,sequence INTEGER NOT NULL,request_id TEXT NOT NULL,
                    payload TEXT NOT NULL,created TEXT NOT NULL,acknowledged_event_sequence INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(monitor_id,sequence),UNIQUE(monitor_id,request_id));
                CREATE TABLE IF NOT EXISTS forward_assessments (
                    monitor_id TEXT NOT NULL,request_id TEXT NOT NULL,declaration TEXT NOT NULL,
                    snapshot TEXT NOT NULL,analysis_id TEXT UNIQUE NOT NULL,
                    PRIMARY KEY(monitor_id,request_id));
                CREATE TABLE IF NOT EXISTS forward_report_refs (
                    monitor_id TEXT NOT NULL,analysis_id TEXT NOT NULL,role TEXT NOT NULL,
                    PRIMARY KEY(monitor_id,analysis_id,role));
                CREATE TABLE IF NOT EXISTS forward_source_refs (
                    monitor_id TEXT NOT NULL,source_id TEXT NOT NULL,
                    PRIMARY KEY(monitor_id,source_id));
                CREATE TABLE IF NOT EXISTS forward_latest_summaries (
                    monitor_id TEXT PRIMARY KEY,analysis_id TEXT NOT NULL,payload TEXT NOT NULL);
            ''')

    def check(self,declaration):
        declaration=MonitorDeclaration.model_validate(declaration)
        if declaration.policy_binding:
            if self.resolve_policy is None:raise ValueError('Current-policy authority is unavailable; no paper/actual binding can be admitted.')
            policy=self.resolve_policy(declaration)
            if not isinstance(policy,dict) or not policy.get('package') or not policy.get('application_report_sha256'):
                raise ValueError('Policy resolver must return its authoritative package and saved application evidence.')
            if policy['package'].get('package_sha256')!=declaration.policy_binding.package_sha256:
                raise ValueError('Resolved policy differs from the requested frozen family member.')
            actual=declaration.instrument.model_dump(mode='json');expected=policy.get('instrument',{})
            if (any(actual[key]!=expected.get(key) for key in ('symbol','currency'))
                    or any(Decimal(actual[key])!=Decimal(expected[key]) for key in ('tick_size','point_value'))):
                raise ValueError('Observation instrument differs from the authoritative selected policy.')
        else:
            policy=dict(kind='synthetic_diagnostic',package=None,source_backtest_id=None,
                recommendation_status='NO_DEPLOYABLE_POLICY',production_qualified=False)
        observation_plan=(check_observation_plan(declaration.forecast_observation,policy,declared_at_utc=utc(self.clock()))
            if declaration.forecast_observation is not None else None)
        return dict(status='ADMITTED_FOR_OBSERVATION',policy_snapshot=deepcopy(policy),forecast_observation_plan=observation_plan,
            observation_kind=declaration.observation_kind,capabilities=dict(order_placement=False,
            direct_broker_connection=False,immutable_supplied_events=True),
            readiness=dict(production_qualified=False,direct_execution_integration=False),
            limitations=['Supplied records and execution claims are not independently verified.',
                'Advisory controls do not cancel, block or submit platform orders.'])

    def create(self,declaration):
        declaration=MonitorDeclaration.model_validate(declaration);payload=canonical(declaration.model_dump(mode='json'))
        with self.analyses.lock:
            with self.analyses.connect() as db:
                row=db.execute('SELECT declaration FROM forward_monitors WHERE id=?',(declaration.monitor_id,)).fetchone()
            if row:
                if canonical(MonitorDeclaration.model_validate_json(row[0]).model_dump(mode='json'))!=payload:
                    raise Conflict('Monitor ID is already bound to a different immutable declaration.')
                return self.get(declaration.monitor_id),False
            checked=self.check(declaration)
            checked['monitor_declaration_sha256']=sha256(payload.encode()).hexdigest()
            checked['source_check_sha256']=digest(checked)
            with self.analyses.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO forward_monitors(id,declaration,policy,created) VALUES (?,?,?,?)',
                    (declaration.monitor_id,payload,canonical(checked),utc(self.clock())))
                policy=checked['policy_snapshot']
                for key,role in [('application_analysis_id','current_application'),('training_analysis_id','phase_training')]:
                    if policy.get(key):db.execute('INSERT INTO forward_report_refs VALUES (?,?,?)',(declaration.monitor_id,policy[key],role))
                if policy.get('source_backtest_id'):db.execute('INSERT INTO forward_source_refs VALUES (?,?)',(declaration.monitor_id,policy['source_backtest_id']))
            return self.get(declaration.monitor_id),True

    def _monitor(self,db,id):
        row=db.execute('SELECT declaration,policy,created,pause_latched,retired FROM forward_monitors WHERE id=?',(id,)).fetchone()
        if not row:raise KeyError('Forward monitor not found.')
        checked=json.loads(row[1]);expected=checked.get('source_check_sha256')
        if (checked.get('monitor_declaration_sha256')!=sha256(row[0].encode()).hexdigest()
                or expected!=digest({k:v for k,v in checked.items() if k!='source_check_sha256'})):
            raise Conflict('Immutable monitor declaration or captured policy evidence changed.')
        return dict(declaration=json.loads(row[0]),source_check=checked,created_at_utc=row[2],
            pause_latched=bool(row[3]),retired=bool(row[4]))

    def _records(self,db,id,maximum=None):
        return [dict(sequence=seq,event=json.loads(payload),received_at_utc=received,batch_id=batch)
            for seq,payload,received,batch in db.execute('SELECT sequence,payload,received,batch_id FROM forward_events WHERE monitor_id=? AND sequence<=? ORDER BY sequence',
                (id,maximum if maximum is not None else 2**63-1))]

    def _controls(self,db,id):
        return [dict(sequence=seq,control=json.loads(payload),received_at_utc=created,acknowledged_event_sequence=ack)
            for seq,payload,created,ack in db.execute('SELECT sequence,payload,created,acknowledged_event_sequence FROM forward_controls WHERE monitor_id=? ORDER BY sequence',(id,))]

    def _verify_inputs(self,db,id,records):
        """New calculations verify accepted events against exact original bytes."""
        batches={}
        for bid,raw_hash,canonical_hash,raw,received in db.execute('SELECT batch_id,raw_sha256,canonical_sha256,raw,received FROM forward_event_batches WHERE monitor_id=?',(id,)):
            if sha256(raw).hexdigest()!=raw_hash:raise Conflict('Original event batch bytes changed.')
            batch=parse_batch(raw)
            if batch.batch_id!=bid or digest(batch.model_dump(mode='json'))!=canonical_hash:
                raise Conflict('Event batch identity or canonical content changed.')
            batches[bid]=(received,{event.event_id:event.model_dump(mode='json') for event in batch.events})
        for index,row in enumerate(records,1):
            received,values=batches.get(row['batch_id'],(None,{}))
            if (row['sequence']!=index or row['received_at_utc']!=received
                    or values.get(row['event']['event_id'])!=row['event']):
                raise Conflict('Accepted event history differs from its original batch/receive-clock evidence.')

    def get(self,id):
        with self.analyses.connect() as db:
            value=self._monitor(db,id);records=self._records(db,id);controls=self._controls(db,id)
            rows=db.execute('SELECT analysis_id,snapshot FROM forward_assessments WHERE monitor_id=? ORDER BY rowid DESC',(id,)).fetchall()
        latest=self.analyses.get(rows[0][0]) if rows else None
        saved=None
        for analysis_id,snapshot in rows:
            if self.analyses.get(analysis_id)['status']=='complete':
                saved=self.report(analysis_id);break
        state='RETIRED' if value['retired'] else 'PAUSED' if value['pause_latched'] else (saved['calculations']['advisory']['state'] if saved else 'WATCH')
        if saved and not value['pause_latched'] and not value['retired'] and controls and controls[-1]['control']['action']=='resume':
            if controls[-1]['control']['acknowledged_snapshot_sha256']==digest(saved):
                state='WATCH' if saved['calculations']['reconciliation']['issues'] else 'ACTIVE'
        value.update(monitor_id=id,advisory_state=state,order_placement_enabled=False,enforcement='advisory_only',
            event_count=len(records),event_head_sha256=digest(records),control_history=controls,
            latest_assessment=latest,last_completed_analysis_id=saved['id'] if saved else None,
            last_completed_snapshot_sha256=digest(saved) if saved else None,
            recovery=saved['calculations']['recovery'] if saved else None,
            assessment_pending=not saved or saved['input_snapshot']['event_head_sha256']!=digest(records),
            state_as_of_utc=saved['calculations']['as_of_utc'] if saved else None,live_state_monitored=False)
        if value['assessment_pending'] and value['advisory_state']=='ACTIVE':value['advisory_state']='WATCH'
        return value

    def list(self,*,application_id=None,limit=50,offset=0,q=''):
        if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or offset<0 or not isinstance(q,str) or len(q)>120:
            raise ValueError('Use 1 to 100 summaries, nonnegative offset and a query of at most120 characters.')
        where=[];args=[]
        if application_id:where.append("json_extract(m.declaration,'$.policy_binding.application_id')=?");args.append(application_id)
        if q:where.append("json_extract(m.declaration,'$.name') LIKE ?");args.append('%'+q+'%')
        clause=' WHERE '+' AND '.join(where) if where else ''
        with self.analyses.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM forward_monitors m'+clause,args).fetchone()[0]
            rows=db.execute("SELECT m.id,json_extract(m.declaration,'$.name'),json_extract(m.declaration,'$.observation_kind'),m.created,m.pause_latched,m.retired,s.analysis_id,s.payload,(SELECT COUNT(*) FROM forward_events e WHERE e.monitor_id=m.id) FROM forward_monitors m LEFT JOIN forward_latest_summaries s ON s.monitor_id=m.id"+clause+' ORDER BY m.created DESC,m.id LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        items=[]
        for id,name,kind,created,paused,retired,analysis_id,payload,count in rows:
            saved=json.loads(payload) if payload else None;pending=not saved or saved['event_count']!=count
            state='RETIRED' if retired else 'PAUSED' if paused else saved['advisory_state'] if saved else 'WATCH'
            if saved and not paused and not retired and state=='PAUSED' and saved['recovery_eligible']:
                state='WATCH' if saved['has_issues'] else 'ACTIVE'
            if pending and state=='ACTIVE':state='WATCH'
            items.append(dict(monitor_id=id,name=name,observation_kind=kind,created_at_utc=created,advisory_state=state,
                event_count=count,assessment_pending=pending,state_as_of_utc=saved['as_of_utc'] if saved else None,
                last_completed_analysis_id=analysis_id,live_state_monitored=False,enforcement='advisory_only'))
        return dict(items=items,total=total,limit=limit,offset=offset,projection_only=True)

    def events(self,id,*,offset=0,limit=100):
        if not 0<=offset or not 1<=limit<=1000:raise ValueError('Use a nonnegative offset and 1 to 1000 records.')
        with self.analyses.connect() as db:self._monitor(db,id);records=self._records(db,id)
        return dict(total=len(records),offset=offset,records=records[offset:offset+limit])

    def _preview(self,db,id,batch,raw,received):
        monitor=self._monitor(db,id);declaration=MonitorDeclaration.model_validate(monitor['declaration'])
        if batch.source_id!=declaration.source.source_id:raise ValueError('Event source differs from the immutable monitor source.')
        prior=db.execute('SELECT raw_sha256 FROM forward_event_batches WHERE monitor_id=? AND batch_id=?',(id,batch.batch_id)).fetchone()
        raw_hash=sha256(raw).hexdigest()
        if prior and prior[0]!=raw_hash:raise Conflict('Batch ID is bound to different original bytes.')
        records=self._records(db,id);known={row['event']['event_id']:row['event'] for row in records};new=[]
        for event in batch.events:
            value=event.model_dump(mode='json');old=known.get(event.event_id)
            if old is not None:
                if old!=value:raise Conflict('Event ID is bound to a different immutable payload; append a correction.')
                continue
            new.append(dict(sequence=len(records)+len(new)+1,event=value,received_at_utc=received,batch_id=batch.batch_id))
        if len(records)+len(new)>100000:raise ValueError('This monitor reached the 100,000-event review limit; start an explicitly linked new monitor.')
        batches,byte_count=db.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(raw)),0) FROM forward_event_batches WHERE monitor_id=?',(id,)).fetchone()
        if not prior and (batches>=1000 or byte_count+len(raw)>32*1024*1024):
            raise ValueError('This monitor reached its 1,000-batch or 32 MiB source-history review limit.')
        try:effective_records(records+new)
        except ValueError as exc:raise Conflict(str(exc)) from exc
        expected_kind={'synthetic_harness':'synthetic','paper':'paper','actual_import':'actual'}[declaration.observation_kind]
        mismatch=[event.event_id for event in batch.events if hasattr(event,'execution_kind') and event.execution_kind!=expected_kind]
        return dict(status='REVIEW_REQUIRED' if mismatch else 'VALIDATED_FOR_IMPORT',
            source_id=batch.source_id,observation_kind=declaration.observation_kind,event_kind_counts=dict(Counter(event.kind for event in batch.events)),
            event_time_range=dict(first_utc=min((event.event_time_utc for event in batch.events),key=stamp),last_utc=max((event.event_time_utc for event in batch.events),key=stamp)),
            execution_provenance_mismatches=mismatch,causal_reconciliation='not_assessed',
            validation_scope='Strict event schema, immutable IDs, source and correction chain. Risk/causal reconciliation requires a separately saved assessment.',
            batch_id=batch.batch_id,raw_sha256=raw_hash,canonical_sha256=digest(batch.model_dump(mode='json')),
            event_count=len(batch.events),new_event_count=len(new),idempotent_event_count=len(batch.events)-len(new),
            existing_batch=bool(prior),received_at_utc=received,new_records=new)

    def _exposure(self,id,batch,raw_hash,received):
        with self.analyses.connect() as db:monitor=self._monitor(db,id)
        if self.record_exposure is None:
            # Production app integration must attach the authoritative journal.
            raise ValueError('Research observation journal is unavailable; supplied financial records cannot bypass access tracking.')
        return self.record_exposure(MonitorDeclaration.model_validate(monitor['declaration']),batch,raw_hash,received)

    def check_events(self,id,raw,*,filename='events.json'):
        batch=parse_batch(raw);received=utc(self.clock())
        exposure=self._exposure(id,batch,sha256(raw).hexdigest(),received)
        with self.analyses.lock,self.analyses.connect() as db:preview=self._preview(db,id,batch,raw,received)
        preview.pop('new_records');preview['research_access']=exposure
        return preview

    def append(self,id,raw,*,filename='events.json'):
        if type(filename) is not str or not 1<=len(filename)<=255:raise ValueError('Supply a bounded descriptive filename.')
        batch=parse_batch(raw);received=utc(self.clock())
        exposure=self._exposure(id,batch,sha256(raw).hexdigest(),received)
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE');preview=self._preview(db,id,batch,raw,received)
            if not preview['existing_batch']:
                db.execute('INSERT INTO forward_event_batches VALUES (?,?,?,?,?,?,?)',(id,batch.batch_id,preview['raw_sha256'],preview['canonical_sha256'],raw,filename,received))
                for row in preview['new_records']:
                    db.execute('INSERT INTO forward_events VALUES (?,?,?,?,?,?)',(id,row['sequence'],row['event']['event_id'],canonical(row['event']),received,batch.batch_id))
        preview.pop('new_records');preview['research_access']=exposure
        return preview

    def submit(self,id,request):
        request=Assessment.model_validate(request);payload=canonical(request.model_dump(mode='json'))
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE');monitor=self._monitor(db,id)
            old=db.execute('SELECT declaration,analysis_id FROM forward_assessments WHERE monitor_id=? AND request_id=?',(id,request.request_id)).fetchone()
            if old:
                if old[0]!=payload:raise Conflict('Assessment request ID is already bound to another clock.')
                return self.analyses.get(old[1])
            records=self._records(db,id);controls=self._controls(db,id);analysis_id=uuid4().hex
            self._verify_inputs(db,id,records)
            snapshot=dict(monitor_id=id,last_event_sequence=len(records),event_head_sha256=digest(records),
                control_head_sha256=digest(controls),as_of_utc=request.as_of_utc,implementation_sha256=self.identity(),
                monitor_declaration_sha256=digest(monitor['declaration']),source_check_sha256=digest(monitor['source_check']),
                pause_latched=monitor['pause_latched'],retired=monitor['retired'],
                acknowledged_incident_sequence=max((row['acknowledged_event_sequence'] for row in controls),default=0),
                raw_batch_sha256=[row[0] for row in db.execute('SELECT raw_sha256 FROM forward_event_batches WHERE monitor_id=? ORDER BY rowid',(id,))])
            source=monitor['source_check']['policy_snapshot'].get('source_backtest_id') or 'forward:'+id
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(analysis_id,digest(snapshot),source,utc(self.clock()),'queued','Queued supplied-event reconciliation',None))
            if not source.startswith('forward:'):db.execute('INSERT INTO analysis_sources VALUES (?,?)',(analysis_id,source))
            db.execute('INSERT INTO forward_assessments VALUES (?,?,?,?,?)',(id,request.request_id,payload,canonical(snapshot),analysis_id))
        self.analyses.worker.submit(self._run,id,analysis_id,snapshot)
        return self.analyses.get(analysis_id)

    def _run(self,id,analysis_id,snapshot):
        try:
            self.analyses._update(analysis_id,'running','Reconciling supplied events at the captured clock')
            if self.identity()!=snapshot['implementation_sha256']:raise Conflict('Reconciliation implementation changed after queueing.')
            with self.analyses.connect() as db:
                monitor=self._monitor(db,id);records=self._records(db,id,snapshot['last_event_sequence'])
                self._verify_inputs(db,id,records)
                batches=[dict(batch_id=batch_id,raw_sha256=raw_hash,filename=filename,received_at_utc=received,raw=raw)
                    for batch_id,raw_hash,filename,received,raw in db.execute('SELECT batch_id,raw_sha256,filename,received,raw FROM forward_event_batches WHERE monitor_id=? ORDER BY rowid',(id,))
                    if raw_hash in snapshot['raw_batch_sha256']]
            if digest(records)!=snapshot['event_head_sha256']:raise Conflict('Captured event history changed.')
            if (digest(monitor['declaration'])!=snapshot['monitor_declaration_sha256']
                    or digest(monitor['source_check'])!=snapshot['source_check_sha256']):raise Conflict('Captured monitor policy changed after queueing.')
            declaration=MonitorDeclaration.model_validate(monitor['declaration'])
            result=reconcile(declaration,records,snapshot['as_of_utc'],pause_latched=snapshot['pause_latched'],retired=snapshot['retired'],
                acknowledged_incident_sequence=snapshot['acknowledged_incident_sequence'])
            policy=monitor['source_check']['policy_snapshot']
            economic=[stamp(row['event']['event_time_utc']) for row in records if row['event']['kind'] not in ('heartbeat','connection','void')]
            earliest_instant=min(economic) if economic else None
            earliest=utc(earliest_instant.isoformat()) if earliest_instant else None
            selection_clock=policy.get('policy_selection_sealed_at_utc')
            publication_clock=policy.get('application_publication_utc')
            policy_clock=publication_clock or selection_clock
            pre_monitor=bool(earliest_instant and earliest_instant<stamp(monitor['created_at_utc']))
            pre_policy=bool(earliest_instant and policy_clock and earliest_instant<stamp(policy_clock))
            result['forward_evidence']=dict(earliest_observed_event_utc=earliest,monitor_created_at_utc=monitor['created_at_utc'],
                authoritative_policy_publication_utc=publication_clock,policy_selection_sealed_at_utc=selection_clock,
                application_reservation_utc=policy.get('application_created_at_utc'),
                conservative_publication_upper_bound_utc=monitor['created_at_utc'] if policy.get('package') else None,
                pre_monitor_history=pre_monitor,pre_policy_history=pre_policy,
                status='SYNTHETIC_ONLY' if declaration.observation_kind=='synthetic_harness' else
                    'RETROSPECTIVE_OR_UNKNOWN_POLICY_SCOPE' if pre_monitor or pre_policy or not policy_clock else 'SUPPLIED_FORWARD_OBSERVATIONS',
                observation_timing_independently_verified=False,eligible_for_future_certification=False)
            forward_evidence=result['forward_evidence']
            package=policy.get('package') or {};forecast_window=package.get('outer_window')
            observed_instants=[value for value in economic if value<=stamp(result['as_of_utc'])]
            observed_start=min(observed_instants) if observed_instants else None
            elapsed=stamp(result['as_of_utc'])-observed_start if observed_start else None
            duration_microseconds=((elapsed.days*86400+elapsed.seconds)*1000000+elapsed.microseconds) if elapsed else 0 if observed_start else None
            from .forward_conformance import evaluate_policy_conformance
            conformance=evaluate_policy_conformance(policy,records,snapshot['as_of_utc'],reconciliation=result)
            if conformance.get('accepted_skip_signal_ids'):
                result=reconcile(declaration,records,snapshot['as_of_utc'],pause_latched=snapshot['pause_latched'],retired=snapshot['retired'],
                    acknowledged_incident_sequence=snapshot['acknowledged_incident_sequence'],
                    accepted_skip_signal_ids=conformance['accepted_skip_signal_ids'])
                # The evidence clocks were computed from immutable source history.
                result['forward_evidence']=forward_evidence
            result['policy_conformance']=conformance
            if conformance.get('status') in ('MISMATCH','INSUFFICIENT_EVIDENCE'):
                paused=conformance['status']=='MISMATCH'
                issue=dict(code='frozen_policy_mismatch' if paused else 'frozen_policy_context_unknown',severity='PAUSED' if paused else 'WATCH',
                    event_id=None,details=dict(reasons=conformance.get('reasons',[])),observed_through_sequence=snapshot['last_event_sequence'],
                    historical_incident=False,acknowledged=False)
                result['reconciliation']['issues'].append(issue)
                result['recovery']['current_blockers'].append(issue)
                result['recovery']['eligible_for_acknowledgement']=False
                result['advisory']['reasons'].append(issue['code'])
                if result['advisory']['state']=='ACTIVE':result['advisory']['state']='WATCH'
                if paused:
                    result['reconciliation']['status']='UNRESOLVED'
                    result['advisory'].update(state='RETIRED' if snapshot['retired'] else 'PAUSED',automatic_pause_latched=True,recovery_required=True)
            result['forecast_comparison']=compare_observation(declaration,policy,monitor['source_check'].get('forecast_observation_plan'),
                records,snapshot['as_of_utc'],monitor_created_at_utc=monitor['created_at_utc'])
            result['forecast_comparison'].setdefault('actual_observation',dict(trader_receipts=result['metrics']['trader_receipts'],
                as_of_utc=result['as_of_utc'],first_economic_event_utc=utc(observed_start.isoformat()) if observed_start else None,
                duration_microseconds=duration_microseconds,complete_lifecycle_coverage_verified=False))
            report=dict(format_version=9,model_version='forward-monitor-v1',settings=dict(ANALYSIS_MODE='forward_monitoring'),
                source_backtest_id=monitor['source_check']['policy_snapshot'].get('source_backtest_id'),monitor_id=id,
                request=monitor['declaration'],source_check=monitor['source_check'],input_snapshot=snapshot,
                observation_provenance=dict(kind=declaration.observation_kind,source=declaration.source.model_dump(mode='json'),
                    broker_connection_verified=False,received_clock='server',receiver_clock_provenance=declaration.source.receiver_clock_provenance,supplied_execution_claim_verified=False),calculations=result)
            with TemporaryDirectory(prefix='.pending-forward-',dir=self.analyses.root) as temp:
                staged=Path(temp)/'report';staged.mkdir()
                for name,value in (('declaration.json',monitor['declaration']),('policy_snapshot.json',monitor['source_check']),
                    ('reconciliation.json',result),('input_snapshot.json',snapshot)):
                    (staged/name).write_text(canonical(value),encoding='utf-8')
                (staged/'events.jsonl').write_text(''.join(canonical(row)+'\n' for row in records),encoding='utf-8')
                (staged/'source_batches').mkdir()
                for batch in batches:
                    if sha256(batch['raw']).hexdigest()!=batch['raw_sha256']:raise Conflict('Original event batch bytes changed.')
                    (staged/'source_batches'/f"{batch['raw_sha256']}.json").write_bytes(batch['raw'])
                (staged/'source_batches.json').write_text(canonical([{key:value for key,value in b.items() if key!='raw'} for b in batches]),encoding='utf-8')
                seal_report(staged,report,analysis_id,self.analyses.get(analysis_id)['created'])
                with self.analyses.lock,self.analyses.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if self.identity()!=snapshot['implementation_sha256']:raise Conflict('Reconciliation implementation changed before publication.')
                    staged.rename(self.analyses.root/analysis_id)
                    db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(analysis_id,canonical(sealed_checks(self.analyses.root/analysis_id))))
                    db.execute("UPDATE analyses SET status='complete',progress='Saved supplied-event assessment ready' WHERE id=?",(analysis_id,))
                    summary=dict(advisory_state=result['advisory']['state'],event_count=snapshot['last_event_sequence'],
                        as_of_utc=result['as_of_utc'],recovery_eligible=result['recovery']['eligible_for_acknowledgement'],
                        has_issues=bool(result['reconciliation']['issues']))
                    db.execute('INSERT OR REPLACE INTO forward_latest_summaries VALUES (?,?,?)',(id,analysis_id,canonical(summary)))
                    # Never clear a pause or retirement accepted during calculation.
                    if result['advisory']['automatic_pause_latched']:
                        db.execute('UPDATE forward_monitors SET pause_latched=1 WHERE id=?',(id,))
        except Exception as exc:
            self.analyses._update(analysis_id,'error','Forward assessment failed',f'{type(exc).__name__}: {exc}')

    def report(self,analysis_id):
        record=self.analyses.get(analysis_id)
        if not record or record['status']!='complete':raise Conflict('Assessment has no completed saved report.')
        if not self.analyses.fingerprint(analysis_id):raise Conflict('Saved assessment artifacts changed.')
        report=json.loads((self.analyses.root/analysis_id/'report.json').read_text())
        if report.get('model_version')!='forward-monitor-v1':raise ValueError('Not a forward assessment.')
        return report

    def snapshots(self,id):
        with self.analyses.connect() as db:
            self._monitor(db,id);rows=db.execute('SELECT analysis_id FROM forward_assessments WHERE monitor_id=? ORDER BY rowid DESC',(id,)).fetchall()
        return [self.analyses.get(row[0]) for row in rows]

    def batches(self,id):
        with self.analyses.connect() as db:
            self._monitor(db,id)
            return [dict(batch_id=bid,raw_sha256=raw,canonical_sha256=canon,bytes=size,filename=name,received_at_utc=received)
                for bid,raw,canon,size,name,received in db.execute('SELECT batch_id,raw_sha256,canonical_sha256,LENGTH(raw),filename,received FROM forward_event_batches WHERE monitor_id=? ORDER BY rowid',(id,))]

    def raw_batch(self,id,batch_id):
        with self.analyses.connect() as db:
            self._monitor(db,id);row=db.execute('SELECT raw,raw_sha256 FROM forward_event_batches WHERE monitor_id=? AND batch_id=?',(id,batch_id)).fetchone()
        if not row:raise KeyError('Source event batch not found.')
        if sha256(row[0]).hexdigest()!=row[1]:raise Conflict('Original event batch bytes changed.')
        return row[0]

    def control(self,id,request):
        request=Control.model_validate(request);payload=canonical(request.model_dump(mode='json'))
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE');monitor=self._monitor(db,id);controls=self._controls(db,id)
            prior=[row for row in controls if row['control']['request_id']==request.request_id]
            if prior:
                if canonical(prior[0]['control'])!=payload:raise Conflict('Control request ID is bound to a different action.')
                return prior[0]
            if monitor['retired']:raise Conflict('A retired monitor cannot be reactivated or edited.')
            if request.action=='resume':
                latest=db.execute('SELECT analysis_id FROM forward_assessments WHERE monitor_id=? ORDER BY rowid DESC LIMIT 1',(id,)).fetchone()
                if not latest:raise Conflict('Assess resolved observations before acknowledging recovery.')
                report=self.report(latest[0]);result=report['calculations'];records=self._records(db,id)
                if digest(report)!=request.acknowledged_snapshot_sha256:raise Conflict('Acknowledge the exact latest immutable report SHA.')
                if report['input_snapshot']['event_head_sha256']!=digest(records):raise Conflict('New observations require assessment before recovery.')
                if not result['recovery']['eligible_for_acknowledgement']:
                    raise Conflict('Resolve active reconciliation/risk blockers before recovery.')
                thresholds=MonitorDeclaration.model_validate(monitor['declaration']).thresholds
                age=(stamp(utc(self.clock()))-stamp(result['as_of_utc'])).total_seconds()
                if not -thresholds.maximum_clock_skew_seconds<=age<=min(thresholds.maximum_heartbeat_age_seconds,thresholds.maximum_market_data_age_seconds):
                    raise Conflict('Recovery requires a recent assessment at the server clock; old or future-dated snapshots cannot establish current health.')
                db.execute('UPDATE forward_monitors SET pause_latched=0 WHERE id=?',(id,))
            elif request.action=='pause':db.execute('UPDATE forward_monitors SET pause_latched=1 WHERE id=?',(id,))
            else:db.execute('UPDATE forward_monitors SET retired=1 WHERE id=?',(id,))
            row=dict(sequence=len(controls)+1,control=request.model_dump(mode='json'),received_at_utc=utc(self.clock()),
                acknowledged_event_sequence=len(records) if request.action=='resume' else 0)
            db.execute('INSERT INTO forward_controls VALUES (?,?,?,?,?,?)',(id,row['sequence'],request.request_id,payload,row['received_at_utc'],row['acknowledged_event_sequence']))
            return row

    def export(self,id,kind):
        with self.analyses.connect() as db:
            monitor=self._monitor(db,id)
            if kind=='declaration.json':return canonical(monitor).encode()
            if kind=='events.jsonl':return ''.join(canonical(row)+'\n' for row in self._records(db,id)).encode()
        raise ValueError('Unsupported forward audit export.')
