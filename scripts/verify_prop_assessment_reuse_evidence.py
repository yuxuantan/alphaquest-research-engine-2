"""Independent read-only arithmetic over normal Prop Sim reuse downloads."""
import json
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

root=Path(__file__).resolve().parents[1]/'docs/evidence/qualified_prop_sim/assessment-reuse'
qualification=json.loads((root/'qualification.json').read_text())
passed=json.loads((root/'business-pass.json').read_text())
failed=json.loads((root/'business-fail.json').read_text())
journey=json.loads((root/'journey.json').read_text())
row,=qualification['calculations']['candidates']
cash=mean(p['cash_received'] for p in row['paths'])
assert cash==13000
assert row['prop_qualification']['status']=='GO'
assert row['prop_qualification']['forward_execution']['status']=='PENDING'
assert passed['calculations']['candidates'][0]['paths']==failed['calculations']['candidates'][0]['paths']==row['paths']
assert cash>=float(passed['assessment']['prop_sim_review']['policy']['limits']['minimum_funded_receipts'])==1
assert cash<float(failed['assessment']['prop_sim_review']['policy']['limits']['minimum_funded_receipts'])==999999
assert passed['calculations']['candidates'][0]['economic_assessment']['verdict']=='PASS'
assert failed['calculations']['candidates'][0]['economic_assessment']['verdict']=='FAIL'
with ZipFile(root/'qualification.zip') as archive:assert json.loads(archive.read('report.json'))==qualification
assert journey['duplicate_reused'] and journey['assessment_count']==3
assert journey['current_tables']==journey['initial_summary_fetches']==1
assert journey['history_summary_fetches_after_opening_one']==2
print(json.dumps(dict(mean_funded_receipts=cash,limits=[1,999999],verdicts=['PASS','FAIL'],
    identical_paths=True,duplicate_created_no_job=True,current_tables=1,
    initial_report_fetches=1,fetches_after_opening_one_history_entry=2),indent=2))
