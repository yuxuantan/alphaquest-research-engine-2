"""Research navigation and editable settings in the existing analysis catalogue.

Drafts/templates never own calculations or access authority. Actual campaigns,
checks, frozen procedures and reports keep their established owners.
"""
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import fields
from hashlib import sha256
import json
import sqlite3
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from .prop.adapter import canonical
from .research import ResearchConflict
from .robust_research import RobustResearchRequest


VERSION = 'research-workspace-v1'
MAX_SETTINGS_BYTES = 512 * 1024
TEMPLATE_KEYS = frozenset(('folds', 'qualification', 'execution_scenarios', 'regimes',
    'economic_studies', 'reliability', 'terminal_selection', 'final_evidence'))
EPHEMERAL_KEYS = frozenset(('campaign_id', 'confirmed_backtest_count',
    'confirmed_economic_candidate_count'))


class DocumentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['research-workspace-v1'] = VERSION
    kind: Literal['nested'] = 'nested'
    name: str = Field(min_length=1, max_length=120)
    revision: int | None = Field(default=None, strict=True, ge=1)

    @field_validator('name')
    @classmethod
    def readable_name(cls, value):
        if not value.strip():
            raise ValueError('Give this saved research configuration a name.')
        return value.strip()


class DraftRequest(DocumentRequest):
    declaration: dict


class TemplateRequest(DocumentRequest):
    settings: dict


def _validate_template_studies(studies):
    """Closed phase settings without inventing source dates or running a search."""
    from .prop.phase_dispatch import module_for
    from .prop.phase_profiles import NativeExecution
    from .prop.phase_search import PhaseCalendar

    def keys(value, contract, path, excluded=()):
        if not isinstance(value, dict):
            raise ValueError(f'Template {path} must be an object.')
        allowed = {field.name for field in fields(contract)} - set(excluded)
        if set(value) - allowed:
            raise ValueError(f'Template {path} contains unsupported settings or evidence identities: {sorted(set(value)-allowed)}')

    for study in studies:
        module = module_for(study['phase'])
        evaluation = study['phase'] == 'evaluation'
        profile = module.EvaluationProfile if evaluation else module.FundedProfile
        sampling = module.EvaluationSamplingConfig if evaluation else module.SamplingConfig
        for value in study['profiles']:
            profile(**value)
        module.SimulationConfig(**study['simulation'])
        sampling(**study['sampling'])
        module.SourceCosts(**study['costs'])
        if evaluation:
            module.SequentialRetry(**(study.get('retry') or {}))
        settings = study['search_settings']
        keys(settings, module.EvaluationSearch if evaluation else module.FundedSearch,
            'phase search', ('source_backtest_id', 'candidates', 'mode'))
        if settings.get('calendar') is not None:
            # Nested calendars derive their starts/coverage from actual folds.
            # Validate only supplied keys here; a fresh preview resolves dates.
            keys(settings['calendar'], PhaseCalendar, 'calendar')
        if settings.get('native_execution') is not None:
            keys(settings['native_execution'], NativeExecution, 'native execution')
        if settings.get('constraints') is not None:
            (module.EvaluationConstraints if evaluation else module.FundedConstraints)(**settings['constraints'])
        if not evaluation and settings.get('conservative_objective') is not None:
            module.FundedHistoricalMean(**settings['conservative_objective'])


def normalized_settings(body, document_type):
    """Validate configuration syntax without inspecting sources or running work."""
    raw = deepcopy(body.declaration if document_type == 'draft' else body.settings)
    if len(canonical(raw).encode()) > MAX_SETTINGS_BYTES:
        raise ValueError('Saved research settings exceed 512 KiB; reduce the declaration.')
    if document_type == 'template':
        if raw.get('baselines'):
            raise ValueError('Source-bound baselines require explicit rebinding; save a draft instead.')
        if set(raw) - TEMPLATE_KEYS:
            raise ValueError('Templates accept research settings only; omit source IDs, baselines, results, access claims and request identities.')
        forbidden = {'source_backtest_id', 'backtest_id', 'optimization_id', 'campaign_id',
            'request_id', 'reservation_id', 'procedure_sha256', 'package_sha256', 'candidate_id',
            'source_configuration_id', 'analysis_id', 'approved_ids', 'selected_candidates',
            'production_qualified', 'untouched_certificate', 'winner', 'ranking', 'metrics',
            'calculations', 'qualification_result', 'source_checks', 'access_evidence',
            'recommendation', 'results', 'selection_seal_sha256', 'frozen_package',
            'deployment_readiness', 'source_id', 'dataset_id', 'input_identity', 'source_sha256'}
        def inspect(value):
            if isinstance(value, dict):
                if set(value) & forbidden:
                    raise ValueError('Templates cannot carry source/result identities or evidence authority.')
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
        inspect(raw)
        checked = RobustResearchRequest.model_validate(dict(raw, campaign_id='0'*32,
            name=body.name, source_backtest_id='0'*32,
            sources=[dict(backtest_id='0'*32, sizes=[1])])).model_dump(mode='json')
        _validate_template_studies(checked['economic_studies'])
        return {key: checked[key] for key in sorted(TEMPLATE_KEYS)}
    for key in EPHEMERAL_KEYS:
        raw.pop(key, None)
    raw['name'] = body.name
    checked = RobustResearchRequest.model_validate(dict(raw, campaign_id='0'*32)).model_dump(mode='json')
    return {key: value for key, value in checked.items() if key not in EPHEMERAL_KEYS}


class ResearchWorkspace:
    def __init__(self, campaigns):
        self.campaigns = campaigns
        self.analyses, self.runs = campaigns.analyses, campaigns.runs
        with self.analyses.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS research_workspace_documents (
                    id TEXT PRIMARY KEY, document_type TEXT NOT NULL CHECK(document_type IN ('draft','template')),
                    kind TEXT NOT NULL, name TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    schema_version TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS research_workspace_documents_type
                    ON research_workspace_documents(document_type,updated_at,id);
            ''')
            if 'schema_version' not in {row[1] for row in db.execute('PRAGMA table_info(research_workspace_documents)')}:
                db.execute("ALTER TABLE research_workspace_documents ADD COLUMN schema_version TEXT NOT NULL DEFAULT 'research-workspace-v1'")

    def _source_summary(self, source):
        kind = 'backtest_id' if source.get('backtest_id') else 'optimization_id'
        id = source[kind]
        table, document, prefix = (('runs', 'manifest', '$.run_metadata') if kind == 'backtest_id'
            else ('optimizations', 'payload', '$'))
        # Constant table/paths; only the identifier is caller supplied.
        paths = ['$.status', prefix+'.research.phase', prefix+'.dataset.name',
            prefix+'.strategy.id', prefix+'.research.plan.is_start', prefix+'.research.plan.is_end',
            prefix+'.source.kind', prefix+'.dataset.id', '$.native_account_control', '$.total_trials']
        fields = ','.join(f"json_extract({document},'{path}')" for path in paths)
        with self.runs.connect() as db:
            row = db.execute(f'SELECT {fields} FROM {table} WHERE id=?', (id,)).fetchone()
        selectable = row is not None and row[0] == 'complete' and row[1] == 'is'
        reason = ('Source is missing from this library.' if row is None else
            'Choose a completed IS source; this source is not eligible.' if not selectable else None)
        missing_trials = []
        if selectable and (row[6] == 'external_trade_export' or row[8]):
            selectable, reason = False, 'Nested research requires an original native strategy IS report, not an imported trade source or controlled account replay.'
        if selectable and (not row[7] or self.campaigns.datasets.get(row[7]) is None):
            selectable, reason = False, 'The source price dataset is missing; the saved report remains available.'
        if selectable and kind == 'optimization_id':
            with self.runs.connect() as db:
                trials = db.execute('''SELECT t.trial,json_extract(t.payload,'$.status'),r.id,
                    json_extract(r.manifest,'$.status'),json_extract(r.manifest,'$.run_metadata.research.phase'),
                    json_extract(r.manifest,'$.run_metadata.source.kind'),json_extract(r.manifest,'$.native_account_control')
                    FROM optimization_trials t LEFT JOIN runs r ON r.id=json_extract(t.payload,'$.run_id')
                    WHERE t.optimization_id=?''', (id,)).fetchall()
            by_number = {trial[0]:trial for trial in trials}
            selected = set(source['trials']) if source.get('trials') is not None else set(by_number)
            missing_trials = sorted(number for number in selected if number not in by_number
                or by_number[number][1] not in (None,'complete') or by_number[number][2] is None
                or by_number[number][3] != 'complete' or by_number[number][4] != 'is'
                or by_number[number][5] == 'external_trade_export' or by_number[number][6])
            if (not selected or missing_trials
                    or (source.get('trials') is None and len(trials) != row[9])):
                selectable, reason = False, 'Selected grid trial reports are missing or incomplete. No candidates have been omitted; restore the grid or explicitly revise the declared sources.'
        return dict(id=id, kind=kind, label=(f'{row[2]} · {row[3]} · {id[:12]}' if row else id),
            selectable=selectable, available=row is not None, reason=reason,
            dataset_name=row[2] if row else None, strategy_id=row[3] if row else None,
            is_start=row[4] if row else None, is_end=row[5] if row else None,
            reference=deepcopy(source), source_kind=row[6] if row else None,
            missing_trials=missing_trials)

    def _document(self, row, *, source_details=True):
        id, document_type, kind, name, revision, created, updated, raw, checksum, version = row
        if sha256(raw.encode()).hexdigest() != checksum:
            raise ResearchConflict('Saved research settings failed their integrity check.')
        payload = json.loads(raw)
        result = dict(schema_version=version, id=id, kind=kind, name=name, revision=revision,
            created_at=created, updated_at=updated, requires_fresh_preview=True,
            editable=version==VERSION,
            warnings=[] if version==VERSION else ['Unsupported saved schema; inspect or download the preserved settings before creating a compatible configuration.'],
            **{('declaration' if document_type == 'draft' else 'settings'): payload})
        if document_type == 'draft' and source_details and version==VERSION:
            summaries = [self._source_summary(source) for source in payload['sources']]
            anchor = self._source_summary(dict(backtest_id=payload['source_backtest_id'], sizes=[1]))
            result.update(source_summaries=summaries, anchor_source=anchor,
                missing_sources=[row for row in [anchor, *summaries] if not row['selectable']])
        return result

    def get_document(self, document_type, id):
        with self.analyses.connect() as db:
            row = db.execute('SELECT * FROM research_workspace_documents WHERE id=? AND document_type=?',
                (id, document_type)).fetchone()
        if row is None:
            raise KeyError('Saved research configuration not found.')
        return self._document(row)

    def save_document(self, document_type, body, id=None):
        payload = canonical(normalized_settings(body, document_type))
        now = datetime.now(timezone.utc).isoformat()
        with self.analyses.lock, self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if id is None:
                if body.revision is not None:
                    raise ValueError('A new configuration has no prior revision.')
                id = uuid4().hex
                db.execute('INSERT INTO research_workspace_documents VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (id, document_type, body.kind, body.name, 1, now, now, payload, sha256(payload.encode()).hexdigest(),VERSION))
            else:
                row = db.execute('SELECT revision,schema_version FROM research_workspace_documents WHERE id=? AND document_type=?',
                    (id, document_type)).fetchone()
                if row is None:
                    raise KeyError('Saved research configuration not found.')
                if row[1] != VERSION:
                    raise ResearchConflict('This saved research configuration uses an unsupported schema version; it cannot be overwritten.')
                if body.revision != row[0]:
                    raise ResearchConflict('This configuration changed in another session. Reload it before saving; your edits have not been applied.')
                db.execute('UPDATE research_workspace_documents SET name=?,revision=revision+1,updated_at=?,payload=?,payload_sha256=? WHERE id=?',
                    (body.name, now, payload, sha256(payload.encode()).hexdigest(), id))
        return self.get_document(document_type, id)

    def delete_document(self, document_type, id, revision):
        with self.analyses.lock, self.analyses.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM research_workspace_documents WHERE id=? AND document_type=?',
                (id, document_type)).fetchone()
            if row is None:
                raise KeyError('Saved research configuration not found.')
            if revision != row[0]:
                raise ResearchConflict('This configuration changed in another session. Reload before deleting.')
            db.execute('DELETE FROM research_workspace_documents WHERE id=?', (id,))

    def list_documents(self, document_type, query='', offset=0, limit=50):
        with self.analyses.connect() as db:
            where = "document_type=? AND instr(lower(name||' '||id),lower(?))>0"
            args = (document_type, query.strip())
            total = db.execute('SELECT COUNT(*) FROM research_workspace_documents WHERE '+where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM research_workspace_documents WHERE '+where+
                ' ORDER BY updated_at DESC,id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return dict(items=[self._document(row, source_details=False) for row in rows],
            total=total, limit=limit, offset=offset)

    def _readiness(self, analysis_id, status):
        result = dict(status='NOT_ASSESSED' if status != 'complete' else 'REVIEW_REQUIRED',
            reasons=['Open the saved research report to review evidence and remaining limits.'],
            production_qualified=False)
        if not analysis_id or status != 'complete':
            return result
        path = self.analyses.root/analysis_id/'report.json'
        try:
            # A catalogue read has a fixed per-row bound; large reports remain
            # available in the ordinary detailed view without being truncated.
            if path.stat().st_size > 2*1024*1024:
                return result
            raw = path.read_bytes()
            with self.analyses.connect() as db:
                seal = db.execute('SELECT payload FROM analysis_report_checks WHERE id=?', (analysis_id,)).fetchone()
            if not seal or sha256(raw).hexdigest() != json.loads(seal[0])['report.json']:
                return dict(status='INTEGRITY_REVIEW_REQUIRED', reasons=['The saved report identity changed.'], production_qualified=False)
            calc = json.loads(raw).get('calculations', {})
            recommendations = calc.get('recommendation') or []
            if recommendations:
                statuses = sorted({row['status'] for row in recommendations})
                result.update(status=statuses[0] if len(statuses) == 1 else 'PHASE_RESULTS_DIFFER',
                    phases=[dict(phase=row['phase'],status=row['status']) for row in recommendations],
                    reasons=sorted({str(reason) for row in recommendations for key in
                        ('evidence_blockers','model_blockers','operational_blockers') for reason in row.get(key, [])}))
            elif (calc.get('reliability') or {}).get('status'):
                result.update(status=calc['reliability']['status'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            result.update(status='INTEGRITY_REVIEW_REQUIRED', reasons=['The saved report needs integrity review.'])
        return result

    def catalogue(self, query='', kind='', phase='', status='', offset=0, limit=50, sort='newest'):
        # This is a projection of the existing catalogue, not a copied result
        # store. Neither GET nor draft/template CRUD calls a numerical owner.
        cte = '''WITH entries AS (
            SELECT c.id,'phase' kind,upper(substr(json_extract(c.manifest,'$.phase'),1,1))||substr(json_extract(c.manifest,'$.phase'),2)||' campaign' name,
                c.created created_at,coalesce(a.created,c.created) updated_at,
                coalesce(a.status,'validated') status,json_extract(c.manifest,'$.phase') phase,
                json_extract(c.manifest,'$.request.source_backtest_id') source_id,c.analysis_id,
                CASE WHEN c.frozen IS NOT NULL THEN 'phase_selection_frozen' ELSE coalesce(a.status,'checked') END stage,
                NULL procedure_sha256,NULL application_id,NULL current_analysis_id,NULL current_status,
                CASE WHEN json_type(c.declaration,'$.search_settings.native_execution')='object' THEN 'native_strategy' ELSE 'saved_trade_path' END backend,
                coalesce(a.status,'validated') campaign_status,NULL final_application_id,NULL final_analysis_id,NULL final_status,
                c.analysis_id primary_analysis_id,NULL primary_purpose,NULL primary_application_id
            FROM research_campaigns c LEFT JOIN analyses a ON a.id=c.analysis_id
            UNION ALL
            SELECT c.id,'nested',json_extract(c.declaration,'$.name'),c.created,
                max(c.created,coalesce(a.created,c.created),coalesce(ca.created,c.created),coalesce(fa.created,c.created)),
                coalesce(la.status,a.status,'validated'),
                CASE json_array_length(c.declaration,'$.economic_studies') WHEN 1 THEN json_extract(c.declaration,'$.economic_studies[0].phase') WHEN 2 THEN 'both' ELSE NULL END,
                json_extract(c.declaration,'$.source_backtest_id'),c.analysis_id,
                CASE WHEN latest.id IS NOT NULL THEN latest.purpose||'_'||coalesce(la.status,'saved')
                    WHEN p.sha256 IS NOT NULL THEN 'procedure_frozen' ELSE coalesce(a.status,'checked') END,
                p.sha256,current.id,current.analysis_id,ca.status,'nested_research',
                coalesce(a.status,'validated'),final.id,final.analysis_id,fa.status,
                coalesce(latest.analysis_id,c.analysis_id),latest.purpose,latest.id
            FROM robust_research c LEFT JOIN analyses a ON a.id=c.analysis_id
                LEFT JOIN research_procedures p ON p.campaign_id=c.id
                LEFT JOIN research_procedure_applications current ON current.rowid=(SELECT x.rowid FROM research_procedure_applications x LEFT JOIN analyses y ON y.id=x.analysis_id WHERE x.campaign_id=c.id AND x.purpose='current_development' ORDER BY coalesce(y.created,'') DESC,x.rowid DESC LIMIT 1)
                LEFT JOIN analyses ca ON ca.id=current.analysis_id
                LEFT JOIN research_procedure_applications final ON final.rowid=(SELECT x.rowid FROM research_procedure_applications x LEFT JOIN analyses y ON y.id=x.analysis_id WHERE x.campaign_id=c.id AND x.purpose='final_verification' ORDER BY coalesce(y.created,'') DESC,x.rowid DESC LIMIT 1)
                LEFT JOIN analyses fa ON fa.id=final.analysis_id
                LEFT JOIN research_procedure_applications latest ON latest.rowid=(SELECT x.rowid FROM research_procedure_applications x LEFT JOIN analyses y ON y.id=x.analysis_id WHERE x.campaign_id=c.id ORDER BY coalesce(y.created,'') DESC,x.rowid DESC LIMIT 1)
                LEFT JOIN analyses la ON la.id=latest.analysis_id
            UNION ALL
            SELECT id,'draft',name,created_at,updated_at,'draft',NULL,
                json_extract(payload,'$.source_backtest_id'),NULL,'draft',NULL,NULL,NULL,NULL,'nested_research',
                'draft',NULL,NULL,NULL,NULL,NULL,NULL
            FROM research_workspace_documents WHERE document_type='draft'
        ), projected AS (
            SELECT e.*,json_extract(r.manifest,'$.run_metadata.dataset.name') source_name,
                json_extract(r.manifest,'$.run_metadata.strategy.id') strategy_id,r.id source_exists
            FROM entries e LEFT JOIN source_catalogue.runs r ON r.id=e.source_id
        ) '''
        where = "WHERE (?='' OR kind=?) AND (?='' OR phase=? OR (phase='both' AND ? IN ('evaluation','funded'))) AND (?='' OR status=?) AND instr(lower(name||' '||id||' '||coalesce(source_id,'')||' '||coalesce(source_name,'')||' '||coalesce(strategy_id,'')),lower(?))>0"
        args = (kind, kind, phase, phase, phase, status, status, query.strip())
        ordering = {'newest':'updated_at DESC,id', 'oldest':'updated_at,id', 'name':'name COLLATE NOCASE,id'}[sort]
        with self.analyses.connect() as db:
            db.execute('ATTACH DATABASE ? AS source_catalogue', (str(self.runs.path),))
            total = db.execute(cte+'SELECT COUNT(*) FROM projected '+where, args).fetchone()[0]
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(cte+'SELECT * FROM projected '+where+
                ' ORDER BY '+ordering+' LIMIT ? OFFSET ?', (*args, limit, offset))]
        items = []
        for row in rows:
            primary = row['primary_analysis_id']
            current = (dict(application_id=row['application_id'], analysis_id=row['current_analysis_id'],
                status=row['current_status']) if row['application_id'] else None)
            final = (dict(application_id=row['final_application_id'], analysis_id=row['final_analysis_id'],
                status=row['final_status']) if row['final_application_id'] else None)
            action = ('resume_draft' if row['kind']=='draft' else
                'open_report' if primary and row['status']=='complete' else 'open_campaign')
            items.append(dict(schema_version=VERSION,id=row['id'],kind=row['kind'],name=row['name'],
                source=dict(id=row['source_id'],name=row['source_name'],available=row['source_exists'] is not None),
                phase=row['phase'],backend=row['backend'],status=row['status'],campaign_status=row['campaign_status'],stage=row['stage'],
                created_at=row['created_at'],updated_at=row['updated_at'],analysis_id=row['analysis_id'],
                procedure=dict(procedure_sha256=row['procedure_sha256']) if row['procedure_sha256'] else None,
                current_application=current,final_application=final,
                readiness=self._readiness(primary,row['status']),
                next_action=dict(kind=action, campaign_id=row['id'] if row['kind']!='draft' else None,
                    draft_id=row['id'] if row['kind']=='draft' else None, analysis_id=primary, source_id=row['source_id'],
                    application_id=row['primary_application_id'],purpose=row['primary_purpose'])))
        return dict(items=items,total=total,limit=limit,offset=offset,sort=sort)


router = APIRouter(prefix='/api/research-workspace', tags=['Research workspace'])


async def call(request, method, *args):
    try:
        return await run_in_threadpool(getattr(request.app.state.research_workspace, method), *args)
    except ResearchConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('')
async def catalogue(request: Request, q: str = Query(default='', max_length=200),
        kind: Literal['','phase','nested','draft'] = '', phase: Literal['','evaluation','funded'] = '',
        status: str = Query(default='', max_length=40), offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100), sort: Literal['newest','oldest','name'] = 'newest'):
    return await call(request,'catalogue',q,kind,phase,status,offset,limit,sort)


@router.get('/drafts')
async def drafts(request: Request, q: str = Query(default='', max_length=200),
        offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    return await call(request,'list_documents','draft',q,offset,limit)


@router.get('/templates')
async def templates(request: Request, q: str = Query(default='', max_length=200),
        offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    return await call(request,'list_documents','template',q,offset,limit)


@router.post('/drafts', status_code=201)
async def create_draft(body: DraftRequest, request: Request):
    return await call(request,'save_document','draft',body)


@router.post('/templates', status_code=201)
async def create_template(body: TemplateRequest, request: Request):
    return await call(request,'save_document','template',body)


@router.get('/drafts/{id}')
async def draft(id: UUID, request: Request):
    return await call(request,'get_document','draft',id.hex)


@router.get('/templates/{id}')
async def template(id: UUID, request: Request):
    return await call(request,'get_document','template',id.hex)


@router.put('/drafts/{id}')
async def update_draft(id: UUID, body: DraftRequest, request: Request):
    return await call(request,'save_document','draft',body,id.hex)


@router.put('/templates/{id}')
async def update_template(id: UUID, body: TemplateRequest, request: Request):
    return await call(request,'save_document','template',body,id.hex)


@router.delete('/drafts/{id}', status_code=204)
async def delete_draft(id: UUID, request: Request, revision: int = Query(ge=1)):
    await call(request,'delete_document','draft',id.hex,revision)
    return Response(status_code=204)


@router.delete('/templates/{id}', status_code=204)
async def delete_template(id: UUID, request: Request, revision: int = Query(ge=1)):
    await call(request,'delete_document','template',id.hex,revision)
    return Response(status_code=204)
