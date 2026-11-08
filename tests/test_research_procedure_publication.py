"""Publication race probe with the real ProcedureStore/AnalysisStore owners."""
from copy import deepcopy
from threading import Event,Thread
from uuid import uuid4

from alphaquest.prop.store import AnalysisStore
from alphaquest.research_procedure_store import ProcedureStore
import alphaquest.research_procedure_store as owner


def test_accepted_cancel_during_sealing_cannot_publish_complete(tmp_path,monkeypatch):
    analyses=AnalysisStore(tmp_path)
    try:
        class Harness(ProcedureStore):
            pass
        h=Harness();h.analyses=analyses;h._init_procedures()
        campaign_id,app_id,analysis_id=[uuid4().hex for _ in range(3)]
        development=dict(dataset=dict(id='source'),sessions=['2026-01-05'])
        inventory=dict(sessions=['2026-01-05'],counts={'2026-01-05':1},
            bounds={'2026-01-05':{}},session_content_sha256={'2026-01-05':'a'*64})
        package=dict(procedure_sha256='b'*64,development=development,evaluated_report={'verified':True},
            terminal_plan={},original_declaration=dict(source_backtest_id='source'))
        campaign=dict(plan=dict(engine_identity='unchanged',economic_studies=[dict(phase='funded')]),analysis_id='evaluated')
        h._procedure=lambda *a,**k:deepcopy(package)
        h._verify_steps=lambda *a:None
        h.get=lambda *a:deepcopy(campaign)
        h._snapshot=lambda *a:({},deepcopy(inventory),deepcopy(development))
        h._qualify_window=lambda *a:({},[],[],None)
        h._select_economic=lambda *a:dict(phases=[],status='NO_QUALIFIED_CONFIGURATION')
        h._prepare_baselines=lambda *a:None
        h._checkpoint=lambda *a:h._application_checkpoint()
        h._journal=lambda *a:[]
        h.report=lambda *a:dict(calculations=dict(reliability=dict(status='INSUFFICIENT_EVIDENCE',phases={})))
        monkeypatch.setattr(analyses,'fingerprint',lambda *a:dict(verified=True))
        with analyses.connect() as db:
            db.execute('INSERT INTO research_procedure_applications VALUES (?,?,?,?,?,?,0)',
                (app_id,campaign_id,'b'*64,'current_development','{}',analysis_id))
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,NULL)',
                (analysis_id,'hash','source','2026-01-01T00:00:00Z','queued','Queued'))
        entered,released=Event(),Event();original=owner.seal_report
        def paused(*args,**kwargs):
            entered.set();assert released.wait(10)
            return original(*args,**kwargs)
        monkeypatch.setattr(owner,'seal_report',paused)
        worker=Thread(target=h._run_application,args=(campaign_id,app_id,analysis_id));worker.start()
        assert entered.wait(10),analyses.get(analysis_id)
        cancelled=h.cancel_application(campaign_id,app_id)
        assert cancelled['cancel_requested'] is True and cancelled['status']=='running'
        released.set();worker.join(10);assert not worker.is_alive()
        saved=analyses.get(analysis_id)
        assert saved['status']!='complete', 'Accepted cancellation was overwritten by completed publication: '+repr(saved)
    finally:
        analyses.close()
