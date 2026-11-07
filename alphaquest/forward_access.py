"""Map supplied forward records into the authoritative research access journal."""
from datetime import datetime
import json
from .research_access import market_domain
from .session_calendar import session_date


def exposure_adapter(guard):
    def record(declaration,batch,raw_sha256,received):
        observed=[e for e in batch.events if e.kind not in ('heartbeat','connection','void')]
        if not observed:return dict(status='NO_MARKET_OR_FINANCIAL_OBSERVATION',protected_conflicts=[])
        sessions=sorted({str(session_date(datetime.fromisoformat(e.event_time_utc.replace('Z','+00:00')))) for e in observed})
        source=dict(version='market-observation-identity-v1',dataset_id=None,raw_sha256=raw_sha256,
            source_timezone='UTC',market_domain=market_domain(declaration.instrument.symbol),symbol=declaration.instrument.symbol,
            convention='cme_chicago_1700_v1',preview_witnesses=[],session_content_sha256={})
        provenance=dict(monitor_id=declaration.monitor_id,batch_id=batch.batch_id,source=declaration.source.model_dump(mode='json'),
            observation_kind=declaration.observation_kind,raw_sha256=raw_sha256,first_received_at_utc=received,
            execution_claim_verified=False)
        # First received clock is immutable. Exact retries return the original
        # access event even when the batch is checked again at a later clock.
        request_id='forward-observation:'+declaration.monitor_id+':'+raw_sha256
        return guard.record_supplied_observation(source,dict(sessions=sessions),provenance=provenance,request_id=request_id)
    return record
