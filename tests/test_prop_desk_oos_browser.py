"""Normal Prop Desk workflow and independent frozen-OOS account oracles."""

import csv
from hashlib import sha256
from io import StringIO
import json
from uuid import uuid4

import httpx
import pytest
from prop_desk_fixtures import desk_calculator_sources

from test_backtests_browser import browser, page, playwright, portal
from test_optimization import wait_job
from test_prop_desk_basket import run
from test_prop_phases import phase_history

SUBSETS = '/api/prop-desk/optimizer/subsets'
OOS = '/api/prop-desk/oos-assessments'


def normal_sources(client, *, empty_oos=False, raw=None, max_hold=2):
    if raw is None:
        raw = phase_history(days=9)
    if empty_oos:
        # Eight identical IS sessions. The ninth is observed and stays flat.
        raw = b'\n'.join((line.split(b',', 2)[0] + b',' + line.split(b',', 2)[1] +
                         b',100,100,100,100,100,60,40') if line.startswith(b'01/15/2026,') else line
                         for line in raw.splitlines()) + b'\n'
    label = 'flat' if empty_oos else 'winning'
    upload = client.post('/api/datasets', params=dict(filename=f'SYNTHETIC-frozen-oos-{label}.csv',
        name=f'SYNTHETIC frozen OOS {label}', source_timezone='UTC', tick_size='.25', point_value='20', symbol='NQ'),
        content=raw)
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()['id']
    launch = client.post('/api/optimizations', json=dict(dataset_id=dataset_id,
        strategy_id='consecutive_green_hold', method='exhaustive', workers=1, automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1,end=1,step=0),
                              hold_minutes=dict(start=1,end=max_hold,step=1), contracts=dict(start=1,end=1,step=0)),
        execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='20',
                                slippage_ticks=0,commission_per_contract_per_side='5'),
        sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-14',
                          oos_start='2026-01-15',oos_end='2026-01-15')))
    assert launch.status_code == 202, launch.text
    saved = wait_job(client, launch.json()['id'])
    assert saved['status'] == 'complete', saved
    items = client.get(f"/api/optimizations/{saved['id']}/results").json()['items']
    members = []
    # Both entries occur simultaneously. The two-minute strategy takes priority
    # because it is first and the weights are equal.
    for trial in sorted(items, key=lambda item:item['parameters']['hold_minutes'], reverse=True):
        source = trial['run_id']
        progress = str(uuid4())
        oos = client.post(f'/api/backtests/{source}/oos', params={'progress_id':progress},
                          json={'request_id':str(uuid4())})
        assert oos.status_code == 201, (oos.text, client.get('/api/progress/'+progress).json())
        members.append(dict(source_backtest_id=source, oos_backtest_id=oos.json()['id'], weight=1))
    assert len(members) == max_hold
    return raw, members


def test_frozen_oos_desktop_and_mobile(page, portal, tmp_path, monkeypatch, desk_calculator_sources):
    evidence = tmp_path / 'prop-desk-oos-evidence'
    evidence.mkdir()
    root = portal['url']
    with httpx.Client(base_url=root, timeout=120) as client:
        raw, members = normal_sources(client)
        alternate_raw, alternate = normal_sources(client, empty_oos=True)
        (evidence/'SYNTHETIC-frozen-oos-winning.csv').write_bytes(raw)
        (evidence/'SYNTHETIC-frozen-oos-flat.csv').write_bytes(alternate_raw)

        def unexpected_bar_parse(*args, **kwargs):
            pytest.fail('Warm OOS sources must not require a full bar parse.')

        monkeypatch.setattr('alphaquest.research_folds.read_bars', unexpected_bar_parse)
        base = dict(members=members, minimum_members=2, minimum_micros=4, maximum_micros=5,
                    phase='evaluation', profile_id='apex-50k-eod')
        parents = dict(
            evaluation=run(client, SUBSETS, base),
            first_year=run(client, SUBSETS, dict(base, phase='funded', funded_size_rule='first_year')),
            flat=run(client, SUBSETS, dict(base, members=alternate)),
            lifetime=run(client, SUBSETS, dict(base, members=alternate, phase='funded',
                                             profile_id='lucidflex-50k', funded_size_rule='account_life',
                                             observation_sessions=300)),
            missing=run(client, SUBSETS, dict(base, members=[dict(members[0], oos_backtest_id=None), members[1]])),
        )
        assert parents['evaluation']['report']['optimizer']['ranking'] == parents['flat']['report']['optimizer']['ranking']
        assert parents['evaluation']['report']['optimizer']['ranking_sha256'] == parents['flat']['report']['optimizer']['ranking_sha256']
        parent_bytes = {}
        for label, job in parents.items():
            parent = job['id']
            parent_bytes[parent] = {name:client.get(f'/api/prop-analyses/{parent}/downloads/{name}').content
                                    for name in ('report.json','analysis.zip')}
            (evidence/f'{label}-parent.json').write_bytes(parent_bytes[parent]['report.json'])

        desk = page.locator('#prop-desk-screen')
        launches = {}

        def run_from_browser(label, mobile=False):
            parent = parents[label]['id']
            if mobile:
                page.set_viewport_size({'width':390,'height':844})
            page.goto(root + '/#prop-desk?analysis=' + parent)
            playwright.expect(desk.get_by_role('heading', name='OOS account assessment')).to_be_visible()
            # Inspection size is deliberately different from the ranked 4 MNQ.
            desk.get_by_label('Inspect tested size').select_option('5')
            with page.expect_response('**/api/prop-desk/oos-assessments') as started:
                desk.get_by_role('button', name='Run OOS account assessment').click()
            assert started.value.status == 202, started.value.text()
            assert started.value.request.post_data_json == {'parent_id':parent}
            id = started.value.json()['id']
            table = desk.get_by_role('table')
            playwright.expect(table.get_by_role('columnheader', name='Out of sample')).to_be_visible(timeout=45000)
            job = client.get('/api/prop-desk/'+id).json()
            assert job['report']['configuration']['micros'] == 4
            assert job['report']['configuration']['allocation'] == dict(micros=[2,2], unused=0)
            assert job['report']['configuration']['parent_id'] == parent
            assert job['report']['calculations']['is']['sessions'] == 8
            assert job['report']['calculations']['oos']['sessions'] == 1
            assert job['report']['calculations']['oos']['path_count'] == 1000
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            report_url = f'/api/prop-analyses/{id}'
            with page.expect_download() as archive:
                desk.get_by_role('link', name='All evidence ZIP ↓').click()
            archive.value.save_as(evidence/f'{label}-assessment.zip')
            for name in ('report.json','oos_account_paths.json','admitted_oos_trades.csv'):
                category = 'downloads' if name == 'report.json' else 'files'
                artifact = client.get(report_url+f'/{category}/{name}')
                assert artifact.status_code == 200
                (evidence/f'{label}-{name}').write_bytes(artifact.content)
            page.reload()
            playwright.expect(table.get_by_role('columnheader', name='Out of sample')).to_be_visible()
            page.screenshot(path=evidence/f'{label}-reopened.png', full_page=True)
            desk.get_by_role('link', name='← Optimise result').click()
            playwright.expect(desk.get_by_role('link', name='Open OOS account assessment')).to_be_visible()
            playwright.expect(desk.get_by_role('img', name='Portfolio and members historical closed-trade equity')).to_be_visible()
            playwright.expect(desk.get_by_role('columnheader', name='Out of sample')).to_be_visible()
            if label == 'evaluation':
                page.screenshot(path=evidence/'evaluation-inline.png', full_page=True)
            launches[label] = id
            return job['report']['calculations']

        evaluation = run_from_browser('evaluation')
        for role in ('is','oos'):
            assert evaluation[role]['outcome_counts'] == dict(passed=1000,breached=0,provider_expired=0)
            assert evaluation[role]['median_trading_days_to_target'] == 4
        ledger = list(csv.DictReader(StringIO((evidence/'evaluation-admitted_oos_trades.csv').read_text())))
        assert len(ledger) == 1 and ledger[0]['source_backtest_id'] == members[0]['oos_backtest_id']
        assert float(ledger[0]['net_pnl']) == 798 and float(ledger[0]['commission']) == 2
        funded = run_from_browser('first_year', mobile=True)
        for role in ('is','oos'):
            assert funded[role]['any_payout_count'] == 1000
            assert funded[role]['mean_trader_receipts'] == funded[role]['mean_account_deductions'] == 13000
            assert funded[role]['breach_before_first_payout_count'] == funded[role]['open_at_window_end'] == 0
        lifetime = run_from_browser('lifetime', mobile=True)
        assert lifetime['reporting_window'] == 300
        assert lifetime['is']['resolved_lifetime_mean_receipts'] == 8995.5
        assert lifetime['oos']['open_at_window_end'] == lifetime['oos']['open_without_payout'] == 1000
        assert lifetime['oos']['any_payout_count'] == lifetime['oos']['mean_trader_receipts'] == 0
        assert lifetime['oos']['resolved_lifetime_mean_receipts'] is None

        flat = run(client, OOS, {'parent_id':parents['flat']['id']})
        metrics = flat['report']['calculations']
        assert metrics['is']['outcome_counts']['passed'] == 1000
        assert metrics['oos']['outcome_counts'] == dict(passed=0,breached=0,provider_expired=1000)
        assert metrics['oos']['median_trading_days_to_target'] is None
        (evidence/'flat-assessment.json').write_bytes(
            client.get(f"/api/prop-analyses/{flat['id']}/downloads/report.json").content)

        missing = client.post(OOS, json={'parent_id':parents['missing']['id']})
        assert missing.status_code == 422 and 'no saved OOS link' in missing.json()['detail']
        (evidence/'missing-source.json').write_bytes(missing.content)
        page.goto(root + '/#prop-desk?analysis=' + parents['missing']['id'])
        playwright.expect(desk.get_by_text(missing.json()['detail'], exact=True)).to_be_visible()
        playwright.expect(desk.get_by_role('button', name='Run OOS account assessment')).to_have_count(0)

        parent = parents['evaluation']['id']
        request = {'parent_id':parent}
        repeat = client.post(OOS, json=request)
        assert repeat.status_code == 202 and repeat.json()['id'] == launches['evaluation']
        assert client.post(OOS, json=dict(request,micros=5)).status_code == 422

        def reject_changed(file, action, status, message):
            original = file.read_bytes()
            try:
                file.write_bytes(original+b'\n')
                rejected = action()
                assert rejected.status_code == status and message in rejected.json()['detail']
                return rejected.json()
            finally:
                file.write_bytes(original)

        saved = portal['app'].state.prop_analyses.root
        source = portal['app'].state.runs.root / members[0]['oos_backtest_id'] / 'trades.csv'
        rejections = dict(source=reject_changed(source, lambda:client.post(OOS,json=request),422,'unavailable or changed'))
        child = saved / launches['evaluation'] / 'oos_account_paths.json'
        rejections['child'] = reject_changed(child, lambda:client.post(OOS,json=request),409,'integrity check')
        rejections['parent'] = reject_changed(saved/parent/'report.json',lambda:client.post(OOS,json=request),409,'integrity check')
        (evidence/'changed-artifacts.json').write_text(json.dumps(rejections,indent=2))
        for id, files in parent_bytes.items():
            for name, content in files.items():
                assert client.get(f'/api/prop-analyses/{id}/downloads/{name}').content == content
        (evidence/'journey.json').write_text(json.dumps(dict(
            evidence_type='Synthetic normal-product frozen OOS assessment',
            members=members, flat_members=alternate,
            parents={key:value['id'] for key,value in parents.items()},
            assessments=dict(launches,flat=flat['id']),
            parent_sha256={key:{name:sha256(raw).hexdigest() for name,raw in files.items()}
                           for key,files in parent_bytes.items()},
            expected=dict(admitted_net=798,evaluation_days=4,apex_funded_receipts=13000,
                          lucid_is_receipts=8995.5,lucid_oos_open=1000),
            sha256={file.name:sha256(file.read_bytes()).hexdigest() for file in sorted(evidence.iterdir())}),indent=2))
