"""Map supplied forward records into the authoritative research access journal."""
from datetime import date, datetime, timedelta
import json
from .research_access import market_domain
from .session_calendar import session_date


def exposure_adapter(guard):
    def record(declaration,batch,raw_sha256,received):
        observed=[e for e in batch.events if e.kind not in ('heartbeat','connection','void')]
        if not observed:return dict(status='NO_MARKET_OR_FINANCIAL_OBSERVATION',protected_conflicts=[])
        sessions={str(session_date(datetime.fromisoformat(e.event_time_utc.replace('Z','+00:00')))) for e in observed}
        # Complete supplied coverage also exposes claimed zero-trade outcomes
        # across its declared sessions; no-trade evidence is not untouched data.
        for event in observed:
            if event.kind=='account_coverage' and event.coverage=='complete':
                first,end=date.fromisoformat(event.first_session),date.fromisoformat(event.cutoff_date_exclusive)
                # Retain even a conflicting supplied claim: mismatching the
                # monitor's plan cannot erase already disclosed outcomes.
                sessions.update(str(first+timedelta(days=i)) for i in range((end-first).days))
        if declaration.forecast_observation is not None and any(e.kind=='account_coverage' and e.coverage=='complete' for e in observed):
            sessions.update(declaration.forecast_observation.open_sessions)
        sessions=sorted(sessions)
        source=dict(version='market-observation-identity-v1',dataset_id=None,raw_sha256=raw_sha256,
            source_timezone='UTC',market_domain=market_domain(declaration.instrument.symbol),symbol=declaration.instrument.symbol,
            convention='cme_chicago_1700_v1',preview_witnesses=[],session_content_sha256={})
        declared_source=declaration.source.model_dump(mode='json')
        # The default adds no new fact to earlier immutable access records.
        if declared_source.get('receiver_clock_provenance')=='server_wall_clock':declared_source.pop('receiver_clock_provenance')
        provenance=dict(monitor_id=declaration.monitor_id,batch_id=batch.batch_id,source=declared_source,
            observation_kind=declaration.observation_kind,raw_sha256=raw_sha256,first_received_at_utc=received,
            execution_claim_verified=False)
        # First received clock is immutable. Exact retries return the original
        # access event even when the batch is checked again at a later clock.
        request_id='forward-observation:'+declaration.monitor_id+':'+raw_sha256
        return guard.record_supplied_observation(source,dict(sessions=sessions),provenance=provenance,request_id=request_id)
    return record
