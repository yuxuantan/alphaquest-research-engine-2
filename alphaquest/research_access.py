"""Append-only local price/outcome access and protected final-session windows.

Uses the existing AnalysisStore catalogue. This records the local application
scope, not a universal certificate that nobody inspected prices elsewhere.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .prop.adapter import canonical
from .research import ResearchConflict
from .session_calendar import session_date


_metadata = ContextVar('research_metadata_only', default=False)
_authorization = ContextVar('research_final_authorization', default=None)


@contextmanager
def metadata_only():
    """Internal validation/inventory only; never return price rows under this scope."""
    token = _metadata.set(True)
    try:
        yield
    finally:
        _metadata.reset(token)


@contextmanager
def final_authorization(token_id):
    token = _authorization.set(token_id)
    try:
        yield
    finally:
        _authorization.reset(token)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def _day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('Session dates must use canonical YYYY-MM-DD strings.')
    return value


def observation_identity(stamp, numbers):
    """Formatting-independent exact Decimal/time witness, without rounding."""
    values=[]
    for number in numbers:
        number=Decimal(number)
        if not number.is_finite():raise ValueError('Observation identity requires finite values.')
        sign,digits,exponent=number.as_tuple();digits=list(digits)
        while digits and digits[-1]==0:
            digits.pop();exponent+=1
        values.append([sign if digits else 0,digits,exponent if digits else 0])
    return digest([stamp.astimezone(timezone.utc).isoformat(),values])


def market_domain(symbol):
    from .session_calendar import resolve_calendar
    try:
        resolve_calendar(symbol)
        return 'CME:NASDAQ100'
    except ValueError:
        return None


def source_identity(dataset):
    preview=[]
    for row in dataset.get('preview',[]):
        try:
            stamp=datetime.fromisoformat(row['datetime'].replace('Z','+00:00'))
            preview.append(observation_identity(stamp,[row[key] for key in ('Open','High','Low','Close','Volume','UpVol','DownVol')]))
        except (KeyError,ValueError,TypeError):
            # Historical malformed metadata cannot create positive clean evidence.
            pass
    return dict(version='market-observation-identity-v1',dataset_id=dataset.get('id'),
        raw_sha256=dataset['sha256'],source_timezone=dataset['source_timezone'],
        market_domain=market_domain(dataset.get('symbol')),symbol=dataset.get('symbol',''),
        convention='cme_chicago_1700_v1',preview_witnesses=preview,
        session_content_sha256=deepcopy(dataset.get('session_content_sha256',{})))


def coverage(dataset, date_range=None):
    from .backtest_data import saved_source_timezone
    zone=saved_source_timezone(dataset)
    first=datetime.fromisoformat(dataset['start'].replace('Z','+00:00'))
    last=datetime.fromisoformat(dataset['end'].replace('Z','+00:00'))
    if date_range is not None:
        if getattr(date_range,'convention',None)=='cme_chicago_1700_v1':
            return dict(first_session=(date_range.from_date.isoformat() if date_range.from_date else str(session_date(first))),
                last_session=(date_range.to_date.isoformat() if date_range.to_date else str(session_date(last))))
        if date_range.from_date:
            first=max(first,datetime.combine(date_range.from_date,time.min,zone).astimezone(timezone.utc))
        if date_range.to_date:
            last=min(last,datetime.combine(date_range.to_date,time.max,zone).astimezone(timezone.utc))
    return dict(first_session=str(session_date(first)),last_session=str(session_date(last)))


class ReservationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    first_session:str
    last_session:str
    market_domain:Literal['CME:NASDAQ100']
    external_access:Literal['declared_not_inspected','inspected','unknown']


class ReleaseRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    reason:str=Field(min_length=1,max_length=1000)


class ResearchAccess:
    def __init__(self, analyses, *, fresh_scope=False):
        self.analyses=analyses
        with analyses.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS research_access_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,
                    request_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_access_sources (
                    raw_sha256 TEXT PRIMARY KEY,payload TEXT NOT NULL,disclosure TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_access_meta (key TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research_holdout_reservations (
                    id TEXT PRIMARY KEY,declaration_sha256 TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
            ''')
            now=datetime.now(timezone.utc)
            db.execute('INSERT OR IGNORE INTO research_access_meta VALUES (?,?)',('scope',canonical(dict(
                version='local-application-access-v1',created_at_utc=now.isoformat(),
                complete_from_creation=bool(fresh_scope),legacy_unknown_through_session=str(session_date(now))))))

    def scope(self):
        with self.analyses.connect() as db:
            return json.loads(db.execute('SELECT payload FROM research_access_meta WHERE key=?',('scope',)).fetchone()[0])

    def _append(self,db,request_id,kind,payload):
        value=dict(version='research-access-event-v1',kind=kind,**deepcopy(payload))
        previous=db.execute('SELECT payload FROM research_access_events WHERE request_id=?',(request_id,)).fetchone()
        if previous:
            saved=json.loads(previous[0])
            if {k:v for k,v in saved.items() if k not in ('id','created_at_utc')}!=value:
                raise ResearchConflict('Access request ID is bound to a different immutable action.')
            return saved
        value.update(id=uuid4().hex,created_at_utc=datetime.now(timezone.utc).isoformat())
        db.execute('INSERT INTO research_access_events(id,request_id,kind,payload,sha256) VALUES (?,?,?,?,?)',
            (value['id'],request_id,kind,canonical(value),digest(value)))
        return value

    def register(self,dataset,*,disclosure=None,inventory=None,declared_domain=None):
        source=source_identity(dataset)
        with self.analyses.lock,self.analyses.connect() as db:
            row=db.execute('SELECT payload,disclosure FROM research_access_sources WHERE raw_sha256=?',(source['raw_sha256'],)).fetchone()
            if row:
                old=json.loads(row[0])
                source['dataset_id']=source.get('dataset_id') or old.get('dataset_id')
                source['session_content_sha256']=old.get('session_content_sha256',{})
                source['preview_witnesses']=sorted(set(source['preview_witnesses'])|set(old.get('preview_witnesses',[])))
                source['market_domain']=old.get('market_domain') or source['market_domain']
            if declared_domain:
                if source['market_domain'] and source['market_domain']!=declared_domain:
                    raise ValueError('Declared market domain conflicts with saved instrument lineage.')
                source['market_domain']=declared_domain
            if inventory:
                source['session_content_sha256']=deepcopy(inventory.get('session_content_sha256',{}))
                source['sessions']=deepcopy(inventory['sessions'])
            mode=disclosure or (row[1] if row else 'standard')
            if mode not in ('standard','metadata_only'):raise ValueError('Unknown dataset disclosure mode.')
            # A later default upload cannot silently unhide a protected snapshot.
            if row and row[1]=='metadata_only':mode='metadata_only'
            db.execute('INSERT INTO research_access_sources VALUES (?,?,?) ON CONFLICT(raw_sha256) DO UPDATE SET payload=excluded.payload,disclosure=excluded.disclosure',
                (source['raw_sha256'],canonical(source),mode))
        return source,mode

    def _source(self,db,source):
        row=db.execute('SELECT payload FROM research_access_sources WHERE raw_sha256=?',(source['raw_sha256'],)).fetchone()
        return json.loads(row[0]) if row else source

    def _relation(self,db,source,other,sessions):
        source,other=self._source(db,source),self._source(db,other)
        if source['raw_sha256']==other['raw_sha256']:return 'same'
        if set(source.get('preview_witnesses',[]))&set(other.get('preview_witnesses',[])):return 'same'
        a,b=source.get('session_content_sha256',{}),other.get('session_content_sha256',{})
        if any(day in a and a[day]==b.get(day) for day in sessions):return 'same'
        if source.get('market_domain') and source['market_domain']==other.get('market_domain'):return 'same'
        if not source.get('market_domain') or not other.get('market_domain'):return 'unknown'
        return 'different'

    @staticmethod
    def _intersection(window,sessions):
        if window.get('sessions') is not None:return sorted(set(window['sessions'])&set(sessions))
        return [day for day in sessions if window['first_session']<=day<=window['last_session']]

    @classmethod
    def _interpreted_intersection(cls,window,sessions,source,other):
        """Conservative overlap when identical information uses another clock.

        IANA source-zone interpretations can shift an observation by up to 26
        hours. Two civil dates cover that shift and the CME evening boundary.
        This deliberately favors false overlap over granting a clean history.
        Captured interpretations are compared before raw-hash alias resolution.
        """
        if source.get('source_timezone')==other.get('source_timezone'):
            return cls._intersection(window,sessions)
        if window.get('sessions') is not None:
            expanded={str(date.fromisoformat(day)+timedelta(days=offset)) for day in window['sessions'] for offset in range(-2,3)}
            return sorted(set(sessions)&expanded)
        return cls._intersection(dict(first_session=str(date.fromisoformat(window['first_session'])-timedelta(days=2)),
            last_session=str(date.fromisoformat(window['last_session'])+timedelta(days=2))),sessions)

    def _conflicts(self,db,source,sessions):
        conflicts=[];unknowns=[]
        for sequence,raw,checksum in db.execute('SELECT sequence,payload,sha256 FROM research_access_events ORDER BY sequence'):
            event=json.loads(raw)
            if digest(event)!=checksum:raise ResearchConflict('Access history integrity check failed.')
            if event['kind'] not in ('price_preview','price_download','strategy_execution','price_read','strategy_outcome','legacy_access'):
                continue
            common=self._interpreted_intersection(event['window'],sessions,event['source'],source)
            if not common:continue
            relation=self._relation(db,source,event['source'],common)
            row=dict(event_id=event['id'],sequence=sequence,kind=event['kind'],sessions=common,origin=event.get('origin'))
            if relation=='same':conflicts.append(row)
            elif relation=='unknown':unknowns.append(row)
        return conflicts,unknowns

    def _preview(self,db,source,sessions,external_access):
        conflicts,unknowns=self._conflicts(db,source,sessions)
        scope=json.loads(db.execute('SELECT payload FROM research_access_meta WHERE key=?',('scope',)).fetchone()[0])
        complete=scope['complete_from_creation'] or all(day>scope['legacy_unknown_through_session'] for day in sessions)
        if conflicts:status='PREVIOUSLY_ACCESSED'
        elif unknowns or not self._source(db,source).get('market_domain'):status='UNKNOWN_LINEAGE'
        elif not complete or external_access!='declared_not_inspected':status='INSUFFICIENT_ACCESS_HISTORY'
        else:status='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE'
        return dict(status=status,local_access_clear=(not conflicts and not unknowns) if complete else None,
            conflicts=conflicts,unknowns=unknowns,scope=scope,external_access=external_access,
            external_declaration_verified=False,untouched_certificate=False,
            cross_timezone_overlap_policy='Two civil-date padding for differing captured source timezones; conservative information overlap, not exact market equivalence.',
            checked_through_sequence=db.execute('SELECT COALESCE(MAX(sequence),0) FROM research_access_events').fetchone()[0])

    def preview(self,datasets,dataset_id,body):
        from .research_folds import inventory_sessions
        _day(body.first_session);_day(body.last_session)
        if body.first_session>body.last_session:raise ValueError('Final session range is reversed.')
        dataset=datasets.get(dataset_id)
        if dataset is None:raise KeyError('Dataset not found.')
        with metadata_only():inventory=inventory_sessions(datasets,dataset_id,minimum_sessions=1)
        sessions=[day for day in inventory['sessions'] if body.first_session<=day<=body.last_session]
        if not sessions or sessions[0]!=body.first_session or sessions[-1]!=body.last_session:
            raise ValueError('Final range endpoints must be complete observed session labels; future/missing data remains unavailable.')
        source,_=self.register(dataset,inventory=inventory,declared_domain=body.market_domain)
        with self.analyses.connect() as db:guard=self._preview(db,source,sessions,body.external_access)
        return dict(source=source,proposed_sessions=sessions,session_inventory=inventory,access=guard,
            declaration=body.model_dump(mode='json'))

    def reserve(self,datasets,dataset_id,body):
        preview=self.preview(datasets,dataset_id,body)
        declaration=dict(dataset_id=dataset_id,**body.model_dump(mode='json'))
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT declaration_sha256,payload FROM research_holdout_reservations WHERE id=?',(body.request_id,)).fetchone()
            if row:
                if row[0]!=digest(declaration):raise ResearchConflict('Reservation ID already binds different settings.')
                return json.loads(row[1])
            source,sessions=preview['source'],preview['proposed_sessions']
            for raw, in db.execute("SELECT payload FROM research_holdout_reservations WHERE status IN ('RESERVED','BOUND','CONSUMED')"):
                other=json.loads(raw);common=self._interpreted_intersection(dict(sessions=sessions),other['sessions'],source,other['source'])
                if common and self._relation(db,source,other['source'],common)!='different':
                    raise ResearchConflict('Overlapping market sessions are already reserved or consumed.')
            guard=self._preview(db,source,sessions,body.external_access)
            value=dict(id=body.request_id,status='RESERVED',declaration=declaration,source=source,sessions=sessions,
                access_at_reservation=guard,procedure_sha256=None,application_id=None,token_id=None)
            self._append(db,'reserve:'+body.request_id,'reservation_created',dict(reservation=value))
            db.execute('INSERT INTO research_holdout_reservations VALUES (?,?,?,?)',
                (body.request_id,digest(declaration),'RESERVED',canonical(value)))
            return value

    def get(self,id):
        with self.analyses.connect() as db:
            row=db.execute('SELECT payload FROM research_holdout_reservations WHERE id=?',(id,)).fetchone()
        if not row:raise KeyError('Final reservation not found.')
        return json.loads(row[0])

    def list(self,dataset_id):
        with self.analyses.connect() as db:
            return [value for raw, in db.execute('SELECT payload FROM research_holdout_reservations ORDER BY rowid DESC')
                    if (value:=json.loads(raw))['declaration']['dataset_id']==dataset_id]

    def bind(self,id,procedure_sha256,*,db=None):
        if db is None:
            with self.analyses.lock,self.analyses.connect() as connection:
                connection.execute('BEGIN IMMEDIATE')
                return self.bind(id,procedure_sha256,db=connection)
        row=db.execute('SELECT payload FROM research_holdout_reservations WHERE id=?',(id,)).fetchone()
        if not row:raise KeyError('Final reservation not found.')
        value=json.loads(row[0])
        if value['status']=='BOUND' and value['procedure_sha256']==procedure_sha256:return value
        if value['status']!='RESERVED':raise ResearchConflict('Reservation is already bound, released or consumed.')
        value.update(status='BOUND',procedure_sha256=procedure_sha256)
        self._append(db,'bind:'+id,'reservation_bound',dict(reservation_id=id,procedure_sha256=procedure_sha256))
        db.execute('UPDATE research_holdout_reservations SET status=?,payload=? WHERE id=?',('BOUND',canonical(value),id))
        return value

    def release(self,id,body):
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE');value=self.get(id)
            if value['status'] not in ('RESERVED','BOUND','RELEASED'):
                raise ResearchConflict('A consumed final assessment remains in access history.')
            self._append(db,body.request_id,'reservation_released',dict(reservation_id=id,reason=body.reason))
            value['status']='RELEASED'
            db.execute('UPDATE research_holdout_reservations SET status=?,payload=? WHERE id=?',('RELEASED',canonical(value),id))
            return value

    def authorize_final(self,id,*,procedure_sha256,application_id,selection_seal_sha256,source,allowed_package_sha256):
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE');value=self.get(id)
            binding=dict(reservation_id=id,procedure_sha256=procedure_sha256,application_id=application_id,
                selection_seal_sha256=selection_seal_sha256,source=source,allowed_package_sha256=sorted(allowed_package_sha256),
                window=dict(sessions=value['sessions']))
            if value['status']=='CONSUMED':
                if value.get('authorization_binding')!=binding:raise ResearchConflict('Final data is already consumed by a different immutable application.')
                return value
            if value['status']!='BOUND' or value['procedure_sha256']!=procedure_sha256:
                raise ResearchConflict('Final access requires the bound complete procedure.')
            if self._relation(db,source,value['source'],value['sessions'])!='same':
                raise ResearchConflict('Final source lineage differs from the reserved market history.')
            guard=self._preview(db,source,value['sessions'],value['declaration']['external_access'])
            if guard['status']!='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE':
                raise ResearchConflict('Final data is not eligible: '+guard['status'])
            event=self._append(db,'final:'+application_id,'final_access_authorized',binding)
            value.update(status='CONSUMED',application_id=application_id,token_id=event['id'],authorization_binding=binding)
            db.execute('UPDATE research_holdout_reservations SET status=?,payload=? WHERE id=?',('CONSUMED',canonical(value),id))
            return value

    def assert_deletable(self,dataset):
        with self.analyses.connect() as db:
            for raw, in db.execute("SELECT payload FROM research_holdout_reservations WHERE status IN ('RESERVED','BOUND','CONSUMED')"):
                value=json.loads(raw)
                if value['source']['raw_sha256']==dataset['sha256']:
                    raise ResearchConflict('This source snapshot is retained by a protected or consumed final reservation.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='research_procedures'").fetchone():
                for raw, in db.execute('SELECT payload FROM research_procedures'):
                    value=json.loads(raw)
                    if value['development']['dataset']['sha256']==dataset['sha256']:
                        raise ResearchConflict('This snapshot is retained by an immutable full-procedure freeze.')

    def backfill(self,runs,datasets):
        """Retained outcomes establish prior access; deleted/unknown history stays unknown."""
        available={row['sha256']:row for row in datasets.list()}
        for dataset in available.values():self.register(dataset)
        with runs.connect() as db:
            manifests=[json.loads(row[0]) for row in db.execute('SELECT manifest FROM runs')]
            attempts=list(db.execute('SELECT id,source_sha256,parent_run_id FROM oos_attempts')) if db.execute("SELECT 1 FROM sqlite_master WHERE name='oos_attempts'").fetchone() else []
        by_id={row['id']:row for row in manifests}
        with self.analyses.lock,self.analyses.connect() as db:
            for record in manifests:
                if db.execute('SELECT 1 FROM research_access_events WHERE request_id=?',('retained-report:'+record['id'],)).fetchone():continue
                meta=record.get('run_metadata',{});descriptor=meta.get('dataset',{})
                if not descriptor.get('sha256') or not descriptor.get('source_timezone'):continue
                dataset=dict(descriptor,symbol=meta.get('instrument',{}).get('symbol',''))
                source=source_identity(dataset)
                source['preview_witnesses']=[]
                first,last=record.get('period_start_utc'),record.get('period_end_utc')
                if not first or not last:continue
                window=dict(first_session=str(session_date(datetime.fromisoformat(first.replace('Z','+00:00')))),
                    last_session=str(session_date(datetime.fromisoformat(last.replace('Z','+00:00')))))
                self._append(db,'retained-report:'+record['id'],'strategy_outcome',dict(source=source,window=window,origin='retained_backtest:'+record['id']))
            for attempt_id,sha,parent_id in attempts:
                if db.execute('SELECT 1 FROM research_access_events WHERE request_id=?',('retained-oos-attempt:'+attempt_id,)).fetchone():continue
                record=by_id.get(parent_id);plan=(record or {}).get('run_metadata',{}).get('research',{}).get('plan')
                dataset=available.get(sha)
                if not plan or dataset is None:continue
                from .backtest_data import DateRange
                window=coverage(dataset,DateRange.parse(plan['oos_start'],plan['oos_end']))
                self._append(db,'retained-oos-attempt:'+attempt_id,'legacy_access',dict(source=source_identity(dataset),window=window,origin='retained_oos_attempt:'+attempt_id))

    def record_supplied_observation(self,source,window,*,provenance,request_id):
        """Append external exposure even when a protected reservation overlaps.

        This entry point does not grant reads of reserved datasets. The caller has
        already supplied this separate observation. Keep reservations intact and
        make later clean-access checks fail on the known immutable overlap.
        """
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE');conflicts=[]
            for raw, in db.execute("SELECT payload FROM research_holdout_reservations WHERE status IN ('RESERVED','BOUND','CONSUMED')"):
                reservation=json.loads(raw)
                common=self._interpreted_intersection(window,reservation['sessions'],source,reservation['source'])
                if common and self._relation(db,source,reservation['source'],common)!='different':
                    conflicts.append(dict(reservation_id=reservation['id'],sessions=common,status=reservation['status']))
            payload=dict(source=deepcopy(source),window=deepcopy(window),origin='supplied_forward_observation',
                provenance=deepcopy(provenance),protected_conflicts=conflicts,
                reservation_action='retained; final access eligibility must be rechecked')
            # Reuse existing outcome-access semantics so every current authorization
            # reader sees the observation; no independent side-channel journal.
            prior=db.execute('SELECT payload FROM research_access_events WHERE request_id=?',(request_id,)).fetchone()
            if prior:
                event=json.loads(prior[0])
                old_provenance={k:v for k,v in event['provenance'].items() if k!='first_received_at_utc'}
                new_provenance={k:v for k,v in provenance.items() if k!='first_received_at_utc'}
                if event['source']!=source or event['window']!=window or old_provenance!=new_provenance:
                    raise ResearchConflict('Supplied observation ID changed its immutable source/window/provenance.')
            else:event=self._append(db,request_id,'strategy_outcome',payload)
        return dict(status='RECORDED',event_id=event['id'],protected_conflicts=conflicts,
            synthetic_access_policy='All supplied market/financial observations conservatively affect the market domain, including declared synthetic inputs; the application cannot verify that claimed synthetic prices were never observed.')


    def observe_external(self,normalized,*,origin):
        manifest=normalized['manifest'];instrument=manifest['instrument'];span=manifest['coverage']
        dataset=dict(manifest['dataset'],symbol=instrument['symbol'],source_timezone=manifest['time']['source_timezone'])
        sessions=span.get('sessions')
        # The declared coverage is conservative: an uploaded outcome source has
        # already exposed its entire covered interval, including known empty days.
        window=dict(sessions=sessions) if sessions else dict(first_session=str(session_date(datetime.fromisoformat(span['start_utc'].replace('Z','+00:00')))),last_session=str(session_date(datetime.fromisoformat(span['end_utc'].replace('Z','+00:00')))))
        return self.observe(dataset,window,kind='strategy_outcome',origin=origin)

    def observe(self,dataset,window,*,kind='price_read',origin='internal',request_id=None):
        if _metadata.get():return None
        source,_=self.register(dataset)
        token=_authorization.get()
        with self.analyses.lock,self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for raw, in db.execute("SELECT payload FROM research_holdout_reservations WHERE status IN ('RESERVED','BOUND','CONSUMED')"):
                reservation=json.loads(raw);common=self._interpreted_intersection(window,reservation['sessions'],source,reservation['source'])
                if not common or self._relation(db,source,reservation['source'],common)=='different':continue
                if token is not None and token==reservation.get('token_id') and reservation['status']=='CONSUMED':
                    binding=reservation['authorization_binding']
                    if any(source[key]!=binding['source'][key] for key in ('raw_sha256','source_timezone')):
                        raise ResearchConflict('Final token cannot authorize another source snapshot.')
                    continue
                if reservation['status']=='CONSUMED':
                    # Already accessed data stays available for honest manual
                    # research; it can never receive a fresh clean reservation.
                    continue
                raise ResearchConflict(f'Requested prices ({origin}; {canonical(window)}) overlap protected final sessions. Explicitly release the reservation for ordinary access; prior access cannot later be called untouched.')
            payload=dict(source=source,window=deepcopy(window),origin=origin,authorization_token=token)
            return self._append(db,request_id or 'read:'+digest(dict(kind=kind,**payload)),kind,payload)

    def public_dataset(self,dataset,*,disclosure=None,origin='dataset_metadata'):
        source,mode=self.register(dataset,disclosure=disclosure)
        value=deepcopy(dataset);value['disclosure']=mode
        rows=dataset.get('preview',[])
        sessions=sorted({str(session_date(datetime.fromisoformat(row['datetime'].replace('Z','+00:00')))) for row in rows})
        if mode=='metadata_only':value['preview']=[]
        elif sessions:
            try:self.observe(dataset,dict(sessions=sessions),kind='price_preview',origin=origin)
            except ResearchConflict:
                value['preview']=[];value['disclosure']='protected_final_sessions'
        return value

    def hidden_projection(self,dataset):
        """Suppress protected previews even in nested ordinary API payloads."""
        value=deepcopy(dataset)
        with self.analyses.connect() as db:
            row=db.execute('SELECT disclosure FROM research_access_sources WHERE raw_sha256=?',(dataset['sha256'],)).fetchone()
            mode=row[0] if row else 'standard'
            if mode=='metadata_only':
                value['preview']=[];value['disclosure']=mode
                return value
            source=source_identity(dataset)
            days=sorted({str(session_date(datetime.fromisoformat(row['datetime'].replace('Z','+00:00')))) for row in dataset.get('preview',[])})
            for raw, in db.execute("SELECT payload FROM research_holdout_reservations WHERE status IN ('RESERVED','BOUND')"):
                reservation=json.loads(raw);common=self._interpreted_intersection(dict(sessions=days),reservation['sessions'],source,reservation['source'])
                if common and self._relation(db,source,reservation['source'],common)!='different':
                    value['preview']=[];value['disclosure']='protected_final_sessions';break
        return value


def guard_read(store,dataset_id,date_range=None,*,kind='price_read',origin='native_reader'):
    guard=getattr(store,'research_access',None)
    if guard is None or _metadata.get():return None
    dataset=store.get(dataset_id)
    if dataset is None:raise KeyError('Dataset not found.')
    window=coverage(dataset,date_range)
    if date_range is not None and date_range.active and getattr(date_range,'convention',None)!='cme_chicago_1700_v1':
        # Ordinary ranges use source-local civil dates. A late local clock can
        # label a following CME session that has no selected observations.
        from .research_folds import inventory_sessions
        with metadata_only():inventory=inventory_sessions(store,dataset_id,minimum_sessions=1)
        zone=ZoneInfo(dataset['source_timezone']);days=[]
        for day,bounds in inventory['bounds'].items():
            first=datetime.fromisoformat(bounds['first_utc'].replace('Z','+00:00')).astimezone(zone).date()
            last=datetime.fromisoformat(bounds['last_utc'].replace('Z','+00:00')).astimezone(zone).date()
            if (date_range.from_date is None or last>=date_range.from_date) and (date_range.to_date is None or first<=date_range.to_date):days.append(day)
        guard.register(dataset,inventory=inventory)
        window=dict(sessions=days)
    return guard.observe(dataset,window,kind=kind,origin=origin)


class _ExistingAccessCatalogue:
    """Existing journal access for CLI readers; no worker, recovery, or new DB."""
    def __init__(self,path):
        from threading import RLock
        self.path=path
        self.lock=RLock()

    @contextmanager
    def connect(self):
        import sqlite3
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=30)
        try:
            with db:yield db
        finally:db.close()


def attach_existing_access(datasets):
    path=datasets.path.parent/'prop_analyses'/'catalog.sqlite3'
    if not path.is_file():return
    catalogue=_ExistingAccessCatalogue(path)
    with catalogue.connect() as db:
        present=db.execute("SELECT 1 FROM sqlite_master WHERE name='research_access_meta'").fetchone()
    if present:
        datasets.research_access=ResearchAccess(catalogue,fresh_scope=False)
