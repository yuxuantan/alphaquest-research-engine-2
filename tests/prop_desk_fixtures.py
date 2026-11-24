"""Short synthetic calculator inputs that intentionally bypass the campaign gate.

These fixtures test account arithmetic and saved reports. The qualification
browser journey uses the real campaign gate without this override.
"""

import json

import pytest

from alphaquest import prop_desk
from alphaquest.prop import desk_basket


@pytest.fixture
def desk_calculator_sources(monkeypatch):
    async def fixture_candidates(request):
        runs = request.app.state.runs
        with runs.connect() as db:
            saved = [json.loads(raw) for raw, in db.execute('SELECT manifest FROM runs ORDER BY created_at DESC,id')]
        candidates = {}
        children = []
        for record in saved:
            research = record['run_metadata'].get('research') or {}
            if research.get('phase') == 'oos':
                children.append((record['id'], research.get('parent_run_id')))
            else:
                candidates[record['id']] = None
        for child_id, parent_id in children:
            if parent_id not in candidates or candidates[parent_id] is not None:
                continue
            try:
                desk_basket.checked_record(runs, child_id, 'oos', desk_basket.checked_record(runs, parent_id, 'is'))
            except (ValueError, KeyError):
                continue
            candidates[parent_id] = child_id
        return [dict(source_backtest_id=source, oos_report_id=oos) for source, oos in candidates.items()]

    monkeypatch.setattr(prop_desk, 'qualified_candidates', fixture_candidates)
