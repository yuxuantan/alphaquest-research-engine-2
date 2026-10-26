from pathlib import Path
import subprocess
import pytest
from alphaquest.prop.bridge_engine import guest_path,ps_quote,powershell
from alphaquest.prop.bridge import resolved_settings


def test_guest_paths_and_shell_quoting_preserve_literals():
    path=Path.home()/"a space"/"trade's $(thing).xlsx"
    assert guest_path(path)=="\\\\Mac\\Home\\a space\\trade's $(thing).xlsx"
    assert ps_quote("trade's $(thing)")=="'trade''s $(thing)'"
    command=powershell("Write-Output 'safe'")
    assert '--current-user' in command and '-EncodedCommand' in command
    import base64
    assert base64.b64decode(command[-1]).decode('utf-16-le')=="Write-Output 'safe'"
    with pytest.raises(ValueError,match='home folder'):guest_path('/private/tmp/not-shared.xlsx')


def test_bridge_defaults_are_target_form_and_prices_remain_explicit():
    settings=resolved_settings({})
    assert settings['EVAL_PRICE']=='49' and settings['ACTIVATION_FEE']=='129'
    assert settings['BLOCK_DAYS']=='5' and settings['OUT_OF_SAMPLE_FROM']==''
    alternate=resolved_settings(dict(EVAL_PRICE='109',ACTIVATION_FEE='0'))
    assert alternate['EVAL_PRICE']=='109' and alternate['ACTIVATION_FEE']=='0'


def test_unqualified_bridge_binary_is_rejected(monkeypatch,tmp_path):
    import json
    from types import SimpleNamespace
    import alphaquest.prop.bridge_engine as engine
    binary=tmp_path/'prlctl';binary.write_text('fixture');monkeypatch.setattr(engine,'PRLCTL',str(binary))
    monkeypatch.delenv('ALPHAQUEST_BRIDGE_EXPECTED_SHA256',raising=False)
    monkeypatch.setattr(engine.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps(dict(executable='fixture.exe',sha256='0'*64,version='different'))))
    with pytest.raises(ValueError,match='differs from the qualified'):engine.engine_identity()

@pytest.mark.parametrize('payload',[None,{'status':'error','exit_code':1,'demo':False},{'status':'ok','exit_code':0,'demo':True}])
def test_no_completed_report_for_missing_failed_or_demo_engine_output(monkeypatch,tmp_path,payload):
    import json
    import alphaquest.prop.bridge_engine as engine
    out=tmp_path/'bridge';out.mkdir()
    if payload is not None:(out/'results.json').write_text(json.dumps(payload))
    monkeypatch.setattr(engine,'guest_path',lambda p:str(p))
    class Finished:
        returncode=0
        def poll(self):return 0
    monkeypatch.setattr(engine.subprocess,'Popen',lambda *a,**kw:Finished())
    with pytest.raises(ValueError):engine.run_bridge(tmp_path/'input.xlsx',tmp_path/'settings.json',out,{'executable':'fixture.exe'},lambda p:None)


def test_only_read_only_identity_rpc_is_retried(monkeypatch,tmp_path):
    import json
    from types import SimpleNamespace
    import alphaquest.prop.bridge_engine as engine
    binary=tmp_path/'prlctl';binary.write_text('fixture');monkeypatch.setattr(engine,'PRLCTL',str(binary));monkeypatch.delenv('ALPHAQUEST_BRIDGE_EXPECTED_SHA256',raising=False)
    calls=[]
    def rpc(command,**kw):
        calls.append(command)
        if len(calls)==1:return SimpleNamespace(returncode=255,stdout='',stderr='transient guest RPC')
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(executable='fixture.exe',sha256=engine.QUALIFIED_SHA256,version='qualified')),stderr='')
    monkeypatch.setattr(engine.subprocess,'run',rpc)
    assert engine.engine_identity()['sha256']==engine.QUALIFIED_SHA256
    assert len(calls)==2
    import base64
    assert all('Get-FileHash' in base64.b64decode(c[-1]).decode('utf-16-le') for c in calls)
