"""Chronological account-start replay on verified observed native source rows."""
from copy import copy
from dataclasses import asdict,replace
from datetime import date,timedelta
from hashlib import sha256
from types import SimpleNamespace
from .adapter import canonical


def run(inputs,candidate,search,policy,checkpoint,progress):
    from .native_control import NativeSessionInventory
    from .native_draws import SourceBlock
    from .native_preparation import _make_native_owner,run_prepared_path
    from .assessment_review import start_summary
    original=inputs['catalogue'];programme=copy(inputs['preparation'])
    # Derive an identity-mapped chronological view. All rows/prefix features stay
    # from the checked original catalogue; no sampler or shifted price is used.
    blocks=tuple(SourceBlock(i,i,i+1,s.content_sha256,s.prefix_sha256) for i,s in enumerate(original.sessions))
    c=replace(original,blocks=blocks,block_sessions=1,
        catalogue_sha256=sha256(canonical(dict(parent=original.catalogue_sha256,view='observed-chronological-one-session-v1')).encode()).hexdigest())
    programme.catalogue=c;programme.checked=c
    horizon=policy['start_plan']['horizon_calendar_days'];phase=search.mode.removesuffix('_optimization');paths=[]
    for text in policy['start_plan']['starts']:
        checkpoint();start=date.fromisoformat(text);cutoff=start+timedelta(days=horizon)
        selected=[(i,s) for i,s in enumerate(c.sessions) if start<=s.context.session<cutoff]
        if not selected:raise ValueError('Native account start has no observed source sessions.')
        contexts=NativeSessionInventory({s.context.session:s.context for _,s in selected},start,cutoff)
        dates=set(contexts);closures=[];d=start
        while d<cutoff:
            if d.weekday()<5 and d not in dates:closures.append(str(d))
            d+=timedelta(days=1)
        # Full-window dates were chosen solely from admitted coverage, never P&L.
        pattern=SimpleNamespace(contexts=contexts,phase=phase,start=start,cutoff=cutoff)
        settings=dict(profile=asdict(candidate.profile),sizing=asdict(candidate.sizing),micros=candidate.micros,max_micros=candidate.simulation.max_micros,
            calendar=dict(start_dates=[text],coverage_end=str(cutoff),closures=closures,timezone='America/Chicago',version='verified-observed-native-source-v1'))
        if phase=='evaluation':settings['retry']=asdict(candidate.retry)
        else:settings.update(receipt_delay_calendar_days=search.receipt_delay_calendar_days,receipt_amount_convention='kernel_entitlement_unrounded')
        owner=_make_native_owner(pattern,settings)
        if phase=='evaluation':owner.first_attempt_only=False
        owner.set_detail_capture(True)
        draws=[dict(source_block_index=i,used_sessions=1,target_sessions=[str(s.context.session)],slot=j) for j,(i,s) in enumerate(selected)]
        schedule=dict(draws=draws,path_index=len(paths),schedule_sha256=sha256(canonical(draws).encode()).hexdigest())
        result=run_prepared_path(c,schedule,owner,programme.factory,programme.config,contexts,preparation=programme,checkpoint=checkpoint)['result']
        if phase=='funded':
            result['number_of_payouts']=sum(e['received_within_horizon'] for e in result['payout_events'])
            result['cash_received']=float(result['cash_received']);result['pending_cash']=float(result['pending_cash'])
        paths.append(dict(start_date=text,cutoff_exclusive=str(cutoff),result=result))
        progress(f'Native observed account starts {len(paths)}/{len(policy["start_plan"]["starts"])}')
    return dict(frozen_candidate_id=None,micros=candidate.micros,sizing=asdict(candidate.sizing),paths=paths,summary=start_summary(paths,phase))
