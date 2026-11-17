"""Permanent individual-workflow cleanup, with shared evidence and catalogue safety."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from starlette.concurrency import run_in_threadpool


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def reference_id(value):
    """Pydantic snapshots contain hyphenated UUIDs; catalogue keys use hex."""
    if isinstance(value,str) and len(value) in (32,36):
        try:return UUID(value).hex
        except ValueError:pass
    return value


def references(value):
    """IDs may occur in older nested snapshots as well as today's explicit pins."""
    if isinstance(value,dict):return set().union(set(),*(references(v) for v in value.values()))
    if isinstance(value,list):return set().union(set(),*(references(v) for v in value))
    return {value,reference_id(value)} if isinstance(value,str) else set()


def identity(dataset):
    return dict(sha256=dataset['sha256'],source_timezone=dataset['source_timezone'],
        source_kind=dataset.get('source_kind','native'))


class SourceIdentity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sha256: StrictStr=Field(pattern=r'^[0-9a-f]{64}$')
    source_timezone: StrictStr=Field(min_length=1,max_length=128)
    source_kind: StrictStr=Field(default='native',pattern=r'^(native|external_trade_export)$')


class Preview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    strategy_id: StrictStr=Field(min_length=1,max_length=128)
    source: SourceIdentity
    workflow_id: StrictStr | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')
    group_id: StrictStr | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def one_target(self):
        if (self.workflow_id is None) == (self.group_id is None):
            raise ValueError('Select exactly one workflow or saved-results group; source-wide deletion is not allowed.')
        return self


class Delete(Preview):
    confirmation_sha256: StrictStr=Field(pattern=r'^[0-9a-f]{64}$')


class CampaignDatasetLinks:
    def __init__(self,runs,analyses):
        self.runs=runs;self.analyses=analyses
        with runs.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS campaign_dataset_deletions (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        self.recover()

    @contextmanager
    def connect(self):
        # Both SQLite files use rollback journals: ATTACH provides one atomic
        # super-journal commit, including catalogue rows and the cleanup receipt.
        with self.runs.connect() as db:
            db.execute('ATTACH DATABASE ? AS prop',(str(self.analyses.path),))
            if any(db.execute(f'PRAGMA {schema}.journal_mode').fetchone()[0] not in ('delete','truncate','persist') for schema in ('main','prop')):
                raise ValueError('Permanent deletion needs rollback-journal catalogues; no files were removed.')
            yield db

    def _folders(self,plan):
        return [(self.runs.root,r) for r in plan['run_ids']] + [(self.analyses.root,a) for a in plan['analysis_ids']]

    def recover(self):
        """Recover a pre-commit rename; retry physical cleanup after a committed delete."""
        with self.analyses.lock,self.runs.detail_lock,self.runs.connect() as db:
            for key,raw in db.execute('SELECT id,payload FROM campaign_dataset_deletions').fetchall():
                record=json.loads(raw);plan=record['preview']
                if not record.get('deleted'):
                    for root,id in self._folders(plan):
                        destination=root/UUID(id).hex;staged=root/('.workflow-deleted-'+id)
                        if staged.is_symlink() or destination.is_symlink():raise OSError('Unsafe deletion recovery path.')
                        if staged.exists():
                            if destination.exists():raise OSError('Conflicting workflow deletion recovery paths.')
                            staged.rename(destination)
                    db.execute('DELETE FROM campaign_dataset_deletions WHERE id=?',(key,))
                else:
                    record['cleanup_pending']=self.cleanup(plan)
                    db.execute('UPDATE campaign_dataset_deletions SET payload=? WHERE id=?',(json.dumps(record),key))

    def cleanup(self,plan):
        pending=[]
        for root,id in self._folders(plan):
            staged=root/('.workflow-deleted-'+UUID(id).hex)
            try:
                if staged.is_symlink():raise OSError('Unsafe staged directory.')
                if staged.exists():shutil.rmtree(staged)
            except OSError:pending.append(str(staged))
        return pending

    def preview(self,strategy_id,source,db=None,*,workflow_id=None,group_id=None):
        if db is None:
            with self.analyses.lock,self.runs.detail_lock,self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                return self.preview(strategy_id,source,db,workflow_id=workflow_id,group_id=group_id)
        source=SourceIdentity.model_validate(source).model_dump()
        Preview(strategy_id=strategy_id,source=source,workflow_id=workflow_id,group_id=group_id)
        key=fingerprint([strategy_id,source,workflow_id,group_id]);snapshots=[];blockers=[]
        tables={}
        def rows(table):
            if table not in tables:tables[table]=list(db.execute(f'SELECT * FROM {table}'))
            return tables[table]
        def objects(table,keycol,payloadcol):
            return {r[keycol]:json.loads(r[payloadcol]) for r in rows(table)}
        def block(kind,id,message,href=None):
            item=dict(kind=kind,id=id,message=message)
            if href:item['href']=href
            if item not in blockers:blockers.append(item)
        def matches(dataset):
            return isinstance(dataset,dict) and dataset.get('sha256')==source['sha256'] and dataset.get('source_timezone')==source['source_timezone'] and dataset.get('source_kind','native')==source['source_kind']
        workflows=objects('campaign_workflows',0,4)
        selected=set()
        if workflow_id is not None:
            saved=workflows.get(workflow_id)
            if not saved or saved['declaration']['strategy_id']!=strategy_id or not matches(saved['declaration']['dataset']):
                raise KeyError('Selected campaign dataset workflow not found.')
            selected.add(workflow_id)
        indexed_groups={r[0]:r for r in rows('library_datasets')}
        if group_id is not None:
            group=indexed_groups.get(group_id)
            if not group or group[1]!=strategy_id or not matches(json.loads(group[2])['dataset']):
                raise KeyError('Selected saved-results group not found.')
        runs=objects('runs',0,2);jobs=objects('optimizations',0,2)
        run_refs={id:references(record) for id,record in runs.items()}
        job_owners={}
        for table in ('campaign_broad_jobs','campaign_narrow_jobs','campaign_oos_jobs'):
            for r in rows(table):job_owners.setdefault(r[0],set()).add(r[1])
        for id,j in jobs.items():
            owner=reference_id(j.get('research',{}).get('workflow_id'))
            if owner:job_owners.setdefault(id,set()).add(owner)
        owned_jobs={id for id,owners in job_owners.items() if owners & selected}
        # A shared batch and all of its outputs remain owned by surviving workflows.
        job_ids={id for id in owned_jobs if job_owners[id]<=selected}
        retained_jobs=[dict(id=id,reasons=['Workflow '+w for w in sorted(job_owners[id]-selected)]) for id in sorted(owned_jobs-job_ids)]
        candidates={id for id,r in runs.items() if reference_id(r.get('run_metadata',{}).get('research',{}).get('workflow_id')) in selected}
        if group_id is not None:
            indexed={r[0] for r in rows('library_runs')}
            for id,r in runs.items():
                meta=r.get('run_metadata',{});dataset=dict(meta.get('dataset') or {})
                if meta.get('source',{}).get('kind')=='external_trade_export':dataset['source_kind']='external_trade_export'
                if id not in indexed and meta.get('strategy',{}).get('id')==strategy_id and matches(dataset):
                    raise ValueError('New saved results appeared. Refresh the deletion preview before proceeding.')
            candidates.update(r[0] for r in rows('library_runs') if r[1]==group_id)
        trials=[(jid,ordinal,json.loads(raw)) for jid,ordinal,raw in rows('optimization_trials')]
        trial_refs={ (jid,ordinal):references(payload) & runs.keys() for jid,ordinal,payload in trials }
        for id in selected:candidates.update(references(workflows[id]) & runs.keys())
        if group_id is not None:
            # Delete only unowned legacy batches whose entire saved result set
            # belongs to this explicit group. Mixed/shared batches remain intact.
            for jid in jobs.keys()-job_owners.keys():
                refs=set().union(set(),*(value for (job,_),value in trial_refs.items() if job==jid))
                if refs and refs<=candidates:job_ids.add(jid)
        for (jid,_),refs in trial_refs.items():
            if jid in job_ids:candidates.update(refs)
        for r in rows('mechanic_job_attempts'):
            if r[1] in selected and r[0] in runs:candidates.add(r[0])
        # Cost-stress / detailed reports can be children of a selected report.
        while True:
            children=set()
            for id,r in runs.items():
                meta=r.get('run_metadata',{})
                if any(meta.get(k) in candidates for k in ('detailed_from_run_id','risk_from_run_id')) or references(r.get('is_screening',{})) & candidates:
                    children.add(id)
                if id in candidates:children.update(references(r.get('is_screening',{})) & runs.keys())
            if children<=candidates:break
            candidates.update(children)
        if not selected and not candidates and not job_ids:raise KeyError('Selected workflow or saved results not found.')
        groups={r[1] for r in rows('library_runs') if r[0] in candidates}
        if group_id is not None:groups.add(group_id)
        sanity=rows('prop.campaign_sanity_jobs');sanity_ids={r[0] for r in sanity if r[1] in selected}
        sims=objects('prop.workflow_prop_simulations',0,2)
        sim_ids=set()
        for id,s in sims.items():
            declared={reference_id(item.get('workflow_id')) for item in s.get('configuration',{}).get('selections',[]) if item.get('workflow_id')}
            # An explicit surviving workflow owner wins over shared run IDs.
            # A portfolio including the selected workflow is one listed cascade.
            if declared:
                if declared & selected:sim_ids.add(id)
            elif references(s) & (selected | sanity_ids | candidates | job_ids):sim_ids.add(id)
        phase_links=rows('prop.workflow_prop_sim_phases')
        campaign_ids={r[2] for r in phase_links if r[0] in sim_ids}
        for id in sim_ids:
            expected=sims[id].get('campaign_ids',{})
            actual={r[1]:r[2] for r in phase_links if r[0]==id}
            if actual!=expected:block('inconsistent_simulation',id,'Downstream simulation phase references are inconsistent; repair them before deleting.')
            campaign_ids.update(expected.values())
        analysis_rows={r[0]:r for r in rows('prop.analyses')}
        analysis_ids=set(sanity_ids)
        for id in sim_ids:analysis_ids.update(references(sims[id].get('portfolio',{})) & analysis_rows.keys())
        campaign_rows=rows('prop.research_campaigns');campaign_analyses=rows('prop.campaign_analyses');assessments=rows('prop.campaign_assessments')
        for r in campaign_rows:
            if r[0] in campaign_ids and r[4]:analysis_ids.add(r[4])
        analysis_ids.update(r[1] for r in campaign_analyses if r[0] in campaign_ids)
        for _,cid,raw in assessments:
            if cid in campaign_ids:analysis_ids.update(references(json.loads(raw)) & analysis_rows.keys())
        analysis_sources=rows('prop.analysis_sources')
        analysis_ids.update(r[0] for r in analysis_sources if r[1] in candidates)
        analysis_ids.update(id for id,r in analysis_rows.items() if r[2] in candidates)
        # Nested studies are explicit downstream owners, not undeletable locks.
        # Use real source/step edges, never historical prior_access inventories:
        # merely observing another report must not select its entire study.
        studies={r[0]:r for r in rows('prop.robust_research')}
        study_steps={id:[] for id in studies}
        for row in rows('prop.robust_research_steps'):
            study_steps.setdefault(row[0],[]).append(row)
        study_refs={};study_outputs={};study_analyses={}
        for id,row in studies.items():
            declaration=json.loads(row[2]);plan=json.loads(row[3])
            refs=references(declaration.get('source_backtest_id')) | references(declaration.get('sources',[]))
            refs.update(reference_id(c.get('source_backtest_id')) for c in plan.get('candidates',[]))
            refs.update(rid for cid,rid in rows('prop.campaign_sources') if cid==id)
            refs.update(jid for cid,jid in rows('prop.campaign_jobs') if cid==id)
            aids={aid for cid,aid in campaign_analyses if cid==id}
            if row[4]:aids.add(row[4])
            outputs={rid for rid,r in runs.items() if reference_id(r.get('run_metadata',{}).get('research',{}).get('campaign_id'))==id}
            for step in study_steps.get(id,[]):
                payload=json.loads(step[2])
                if payload.get('kind','backtest')=='phase_analysis' and payload.get('analysis_id'):
                    aids.add(reference_id(payload['analysis_id']))
                for phase in payload.get('result',{}).get('phases',[]):
                    if phase.get('analysis_id'):aids.add(reference_id(phase['analysis_id']))
                for baseline in payload.get('result',{}).get('baseline_results',[]):
                    if baseline.get('analysis_id'):aids.add(reference_id(baseline['analysis_id']))
            study_refs[id]=refs | aids | outputs
            study_outputs[id]=outputs;study_analyses[id]=aids
        study_ids=set()
        # Native percentage/OOS assessments publish controlled backtests in the
        # normal RunStore. Include those owned outputs, not just their source
        # reports, and follow any analyses of those outputs to a fixed point.
        while True:
            before=(len(candidates),len(analysis_ids),len(study_ids))
            for id,refs in study_refs.items():
                if refs & (candidates | analysis_ids | job_ids | campaign_ids | sim_ids | selected):
                    study_ids.add(id)
            for id in study_ids:
                candidates.update(study_outputs[id]);analysis_ids.update(study_analyses[id] & analysis_rows.keys())
            for id,r in runs.items():
                meta=r.get('run_metadata',{});research=meta.get('research') or {}
                control=meta.get('native_account_control') or r.get('native_account_control') or {}
                if not isinstance(control,dict):control={}
                if (reference_id(control.get('analysis_id')) in analysis_ids or reference_id(research.get('analysis_id')) in analysis_ids
                        or reference_id(research.get('campaign_id')) in campaign_ids):
                    candidates.add(id)
                if any(meta.get(k) in candidates for k in ('detailed_from_run_id','risk_from_run_id')):
                    candidates.add(id)
            analysis_ids.update(aid for aid,rid in analysis_sources if rid in candidates)
            analysis_ids.update(id for id,r in analysis_rows.items() if r[2] in candidates)
            if before==(len(candidates),len(analysis_ids),len(study_ids)):break
        owner_ids=campaign_ids | study_ids
        groups.update(r[1] for r in rows('library_runs') if r[0] in candidates)
        # External owners keep shared evidence. Never recursively delete an
        # unrelated research campaign, another dataset workflow or live monitor.
        keep_analyses={};keep_runs={}
        def keep(mapping,id,reason):mapping.setdefault(id,set()).add(reason)
        for id in analysis_ids:
            for r in rows('optimization_prop_links'):
                if r[3]==id and r[1] not in job_ids:keep(keep_analyses,id,f'Backtest batch {r[1]}')
            for rid,r in runs.items():
                if rid not in candidates and id in run_refs[rid]:keep(keep_analyses,id,f'Saved backtest {rid}')
            for cid,aid in campaign_analyses:
                if aid==id and cid not in owner_ids:keep(keep_analyses,id,f'Research campaign {cid}')
            for row in campaign_rows:
                if row[4]==id and row[0] not in campaign_ids:keep(keep_analyses,id,f'Research campaign {row[0]}')
            for aid,wid,_ in sanity:
                if aid==id and wid not in selected:keep(keep_analyses,id,f'Workflow {wid}')
            for sid,s in sims.items():
                if sid not in sim_ids and id in references(s):keep(keep_analyses,id,f'Prop Sim {sid}')
            for sid,refs in study_refs.items():
                if sid not in study_ids and id in refs:keep(keep_analyses,id,f'Nested research {sid}')
            for table in ('forward_report_refs','forward_assessments'):
                for r in rows('prop.'+table):
                    if id in r:keep(keep_analyses,id,f'Forward monitor {r[0]}')
            for request,_,_,aid in rows('prop.lifecycle_comparisons'):
                if aid==id:keep(keep_analyses,id,f'Lifecycle comparison {request}')
        workflow_pins={id:references(w) & runs.keys() for id,w in workflows.items()}
        for table in ('campaign_broad_state','campaign_narrow_state'):
            for r in rows(table):workflow_pins.setdefault(r[0],set()).update(references(json.loads(r[-1])) & runs.keys())
        for r in rows('campaign_workflow_runs'):workflow_pins.setdefault(r[0],set()).add(r[1])
        for r in rows('mechanic_job_attempts'):
            if r[0] in runs:workflow_pins.setdefault(r[1],set()).add(r[0])
        for id in candidates:
            for (jid,_),refs in trial_refs.items():
                if jid not in job_ids and id in refs:keep(keep_runs,id,f'Backtest batch {jid}')
            for wid,pins in workflow_pins.items():
                if wid not in selected and id in pins:keep(keep_runs,id,f'Workflow {wid}')
            for cid,rid in rows('prop.campaign_sources'):
                if rid==id and cid not in owner_ids:keep(keep_runs,id,f'Research campaign {cid}')
            for monitor,rid in rows('prop.forward_source_refs'):
                if rid==id:keep(keep_runs,id,f'Forward monitor {monitor}')
            for aid,rid in analysis_sources:
                if rid==id and (aid not in analysis_ids or aid in keep_analyses):keep(keep_runs,id,f'Prop analysis {aid}')
            for aid,r in analysis_rows.items():
                if r[2]==id and (aid not in analysis_ids or aid in keep_analyses):keep(keep_runs,id,f'Prop analysis {aid}')
        for table in ('research_procedures','research_procedure_applications','robust_research','robust_research_steps'):
            for row in rows('prop.'+table):
                if table in ('robust_research','robust_research_steps') and row[0] in study_ids:continue
                refs=set()
                for value in row:
                    if isinstance(value,str):
                        try:refs.update(references(json.loads(value)))
                        except (ValueError,TypeError):refs.add(value)
                for id in refs & candidates:keep(keep_runs,id,f'{table} {row[0]}')
        # Keep the transitive evidence of every surviving owner. This includes
        # automatic analyses referenced by a shared backtest and their own sources.
        while True:
            before=(len(keep_runs),len(keep_analyses))
            for id in runs:
                if id not in candidates or id in keep_runs:
                    for child in run_refs[id] & candidates:
                        if child!=id:keep(keep_runs,child,f'Saved backtest {id}')
                    for aid in run_refs[id] & analysis_ids:keep(keep_analyses,aid,f'Saved backtest {id}')
            for aid,rid in analysis_sources:
                if aid in keep_analyses and rid in candidates:keep(keep_runs,rid,f'Prop analysis {aid}')
            for aid,r in analysis_rows.items():
                if aid in keep_analyses and r[2] in candidates:keep(keep_runs,r[2],f'Prop analysis {aid}')
            if before==(len(keep_runs),len(keep_analyses)):break
        for id in selected:
            if workflows[id].get('status') in ('running','queued'):block('active_workflow',id,'Stop the running mechanics job before deleting.','#jobs')
        for r in rows('mechanic_job_attempts'):
            if r[1] in selected and r[5] in ('running','queued'):block('active_job',r[0],'Stop the running mechanics job before deleting.','#jobs')
        for id in job_ids | owned_jobs:
            if jobs[id]['status'] in ('running','queued'):block('active_job',id,'Stop the running backtest batch before deleting.',f'#jobs/backtest_batch/{id}')
        for id in analysis_ids:
            if id in analysis_rows and analysis_rows[id][4] in ('running','queued'):block('active_job',id,'Stop the running prop or Monte Carlo job before deleting.',f'#jobs/prop_analysis/{id}')
        for id in candidates & self.runs.detail_active:block('active_detail',id,'Wait for report detail generation before deleting.')
        for id in sim_ids:
            auto=sims[id].get('automation',{})
            if auto and not auto.get('stop_requested') and any(phase.get('stage') not in ('complete','cancelled','error','no_eligible_candidates') for phase in auto.get('phases',{}).values()):
                block('automation',id,'Stop the automatic simulation before deleting.',f'#prop-sim?analysis={id}')
        # These owners have live/research semantics outside this cleanup action.
        for table in ('research_procedures','research_procedure_applications','robust_research','robust_research_steps','forward_monitors','lifecycle_comparisons'):
            for r in rows('prop.'+table):
                if table in ('robust_research','robust_research_steps') and r[0] in study_ids:continue
                refs=set()
                for v in r:
                    if isinstance(v,str):
                        try:refs.update(references(json.loads(v)))
                        except (ValueError,TypeError):refs.add(v)
                if refs & (owner_ids | sim_ids | job_ids | selected | analysis_ids):block(table,r[0],f'{table} {r[0]} retains a downstream package. Remove that dependency first.')
        for cid,jid in rows('prop.campaign_jobs'):
            if jid in job_ids and cid not in owner_ids:block('research_campaign',cid,'A separate research campaign retains this backtest batch.',f'#backtests/prop/campaign/{cid}')
        run_ids=sorted(candidates-keep_runs.keys());delete_analyses=sorted(analysis_ids-keep_analyses.keys())
        files=[]
        for kind,root,ids in [('backtest',self.runs.root,run_ids),('analysis',self.analyses.root,delete_analyses)]:
            for id in ids:
                if UUID(id).hex!=id:raise ValueError('Noncanonical report identity; no files were removed.')
                folder=root/id
                if folder.is_symlink():block('unsafe_file',id,'Report directory is a symbolic link; no deletion is allowed.');continue
                for path in sorted(folder.rglob('*')) if folder.exists() else []:
                    if path.is_symlink():block('unsafe_file',id,'Report contains a symbolic link; no deletion is allowed.')
                    elif path.is_file():files.append(dict(kind=kind,id=id,path=str(path.relative_to(root)),bytes=path.stat().st_size))
        # Bind confirmation to frozen packages, dependencies and result membership.
        for table,ids,index in [('campaign_workflows',selected,0),('runs',candidates,0),('optimizations',job_ids,0),('prop.workflow_prop_simulations',sim_ids,0),('prop.research_campaigns',campaign_ids,0),('prop.analyses',analysis_ids,0)]:
            snapshots.extend([table,list(r)] for r in rows(table) if r[index] in ids)
        for table in ('robust_research','robust_research_steps','campaign_sources','campaign_jobs','campaign_analyses'):
            snapshots.extend(['prop.'+table,list(r)] for r in rows('prop.'+table) if r[0] in study_ids)
        dataset=next((workflows[id]['declaration']['dataset'] for id in sorted(selected)),None)
        if dataset is None:dataset=next((runs[id]['run_metadata']['dataset'] for id in sorted(candidates)),{})
        result=dict(strategy_id=strategy_id,source=source,source_key=key,workflow_id=workflow_id,group_id=group_id,
            dataset_name=dataset.get('name','Saved dataset'),retained_jobs=retained_jobs,
            workflow_ids=sorted(selected),group_ids=sorted(groups),job_ids=sorted(job_ids),run_ids=run_ids,
            simulation_ids=sorted(sim_ids),phase_campaign_ids=sorted(campaign_ids),analysis_ids=delete_analyses,
            research_study_ids=sorted(study_ids),
            research_studies=[dict(id=id,name=json.loads(studies[id][2]).get('name','Nested research'),
                created_at_utc=studies[id][1],analysis_id=studies[id][4],
                status=analysis_rows[studies[id][4]][4] if studies[id][4] in analysis_rows else 'planned',
                saved_steps=len(study_steps.get(id,[]))) for id in sorted(study_ids)],
            retained_runs=[dict(id=id,reasons=sorted(reasons)) for id,reasons in sorted(keep_runs.items())],
            retained_analyses=[dict(id=id,reasons=sorted(reasons)) for id,reasons in sorted(keep_analyses.items())],
            files=files,file_count=len(files),bytes=sum(f['bytes'] for f in files),blockers=blockers,deletable=not blockers,
            interpretation='Permanently delete only the selected workflow (or saved-results group), its unshared phase evidence and the listed downstream research studies and Prop Sim/portfolio analyses. Other workflows using this dataset remain. Original datasets, campaign definitions, shared evidence and research-access history stay intact. There is no Undo.')
        result['confirmation_sha256']=fingerprint([result,snapshots])
        return result

    def delete(self,body):
        moved=[];key=body.confirmation_sha256
        with self.analyses.lock,self.runs.detail_lock:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT payload FROM campaign_dataset_deletions WHERE id=?',(key,)).fetchone()
                if old:
                    record=json.loads(old[0])
                    if record['preview']['source_key']!=fingerprint([body.strategy_id,body.source.model_dump(),body.workflow_id,body.group_id]):raise ValueError('Deletion receipt does not match this source.')
                else:
                    plan=self.preview(body.strategy_id,body.source.model_dump(),db,workflow_id=body.workflow_id,group_id=body.group_id)
                    if key!=plan['confirmation_sha256']:raise ValueError('Dependencies or results changed. Review a fresh deletion preview.')
                    if plan['blockers']:raise ValueError(' '.join(b['message'] for b in plan['blockers']))
                    record=dict(deleted=False,preview=plan,cleanup_pending=[])
                    db.execute('INSERT INTO campaign_dataset_deletions VALUES (?,?)',(key,json.dumps(record)))
            if not record['deleted']:
                plan=record['preview']
                try:
                    with self.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        fresh=self.preview(body.strategy_id,body.source.model_dump(),db,workflow_id=body.workflow_id,group_id=body.group_id)
                        if fresh['confirmation_sha256']!=key:raise ValueError('Dependencies changed. Review deletion again.')
                        for root,id in self._folders(plan):
                            destination=root/UUID(id).hex;staged=root/('.workflow-deleted-'+id)
                            if staged.exists() or staged.is_symlink():raise ValueError('An unfinished cleanup exists; restart the portal to recover it first.')
                            if destination.exists():destination.rename(staged);moved.append((staged,destination))
                        self.erase(db,plan)
                        record.update(deleted=True,deleted_at_utc=datetime.now(timezone.utc).isoformat())
                        db.execute('UPDATE campaign_dataset_deletions SET payload=? WHERE id=?',(json.dumps(record),key))
                except BaseException:
                    for staged,destination in reversed(moved):staged.rename(destination)
                    with self.runs.connect() as db:db.execute('DELETE FROM campaign_dataset_deletions WHERE id=?',(key,))
                    raise
            record['cleanup_pending']=self.cleanup(record['preview'])
            with self.runs.connect() as db:db.execute('UPDATE campaign_dataset_deletions SET payload=? WHERE id=?',(json.dumps(record),key))
            return record

    def erase(self,db,p):
        def delete(table,column,ids):
            db.executemany(f'DELETE FROM {table} WHERE {column}=?',[(id,) for id in ids])
        # Minimal ID tombstones prevent reusing deleted frozen-package IDs.
        # No trades, metrics, declarations or frozen payloads are copied here.
        stamp=datetime.now(timezone.utc).isoformat()
        for sid in p['simulation_ids']:
            receipt=dict(id=sid,deleted=True,deletable=False,deleted_at_utc=stamp,
                         confirmation_sha256=p['confirmation_sha256'],cleanup_pending=[],
                         workflow_deletion=p['source_key'])
            db.execute('INSERT OR IGNORE INTO prop.workflow_prop_sim_deletions VALUES (?,?,?)',
                       (sid,stamp,json.dumps(dict(receipt=receipt))))
        study_ids=p.get('research_study_ids',[])
        for cid in p['phase_campaign_ids']+study_ids:
            receipt=dict(campaign_id=cid,deleted=True,deletable=False,deleted_at_utc=stamp,
                         confirmation_sha256=p['confirmation_sha256'],blockers=[],retained_analyses=[],
                         source_reference_count=0,workflow_deletion=p['source_key'])
            db.execute('INSERT OR IGNORE INTO prop.campaign_deletions VALUES (?,?,?)',
                       (cid,stamp,json.dumps(dict(receipt=receipt))))
        # Owned frozen packages may be removed only as part of this explicitly
        # confirmed family cascade, never through ordinary single-report deletion.
        delete('prop.workflow_prop_sim_phases','simulation_id',p['simulation_ids'])
        delete('prop.workflow_prop_simulations','id',p['simulation_ids'])
        for table in ('campaign_sources','campaign_jobs','campaign_analyses','campaign_assessments'):
            delete('prop.'+table,'campaign_id',p['phase_campaign_ids']+study_ids)
        delete('prop.robust_research_steps','campaign_id',study_ids)
        delete('prop.robust_research','id',study_ids)
        delete('prop.research_campaigns','id',p['phase_campaign_ids'])
        delete('prop.campaign_sanity_jobs','workflow_id',p['workflow_ids'])
        for table,column in [('calculation_reuse','id'),('analysis_report_checks','id'),('historical_refit_checkpoints','analysis_id'),('analysis_sources','analysis_id'),('phase_analysis_control','analysis_id'),('phase_analysis_progress','analysis_id'),('analyses','id')]:
            delete('prop.'+table,column,p['analysis_ids'])
        for table in ('campaign_workflow_runs','mechanic_job_attempts','campaign_broad_jobs','campaign_broad_state','campaign_narrow_jobs','campaign_narrow_state','campaign_oos_jobs','campaign_oos_state'):
            delete(table,'workflow_id',p['workflow_ids'])
        delete('campaign_workflows','id',p['workflow_ids'])
        delete('optimization_trials','optimization_id',p['job_ids'])
        delete('optimizations','id',p['job_ids'])
        # Remove disposable cache hits and legacy OOS navigation references too.
        targets=set(p['run_ids'])
        for key,raw in db.execute('SELECT key,payload FROM optimization_trial_cache').fetchall():
            if references(json.loads(raw)) & targets:db.execute('DELETE FROM optimization_trial_cache WHERE key=?',(key,))
        # OOS access attempts are provenance, not result evidence. Retain them
        # so deleting reports cannot reset prior access or execution counts.
        delete('runs','id',p['run_ids'])
        # A retained shared report keeps its normal saved-results group visible.
        for id in p['group_ids']:
            db.execute('DELETE FROM library_datasets WHERE id=? AND NOT EXISTS (SELECT 1 FROM library_runs WHERE group_id=?)',(id,id))


router=APIRouter(prefix='/api/campaign-dataset-links',tags=['Campaign dataset deletion'])


async def call(request,method,*args,**kwargs):
    try:return await run_in_threadpool(getattr(request.app.state.campaign_dataset_links,method),*args,**kwargs)
    except KeyError as error:raise HTTPException(404,str(error)) from error
    except (ValueError,OSError,sqlite3.Error) as error:raise HTTPException(409,str(error)) from error


@router.post('/preview')
async def preview(body:Preview,request:Request):
    await run_in_threadpool(request.app.state.strategy_library.browser.sync)
    return await call(request,'preview',body.strategy_id,body.source.model_dump(),workflow_id=body.workflow_id,group_id=body.group_id)


@router.delete('')
async def delete(body:Delete,request:Request):
    return await call(request,'delete',body)
