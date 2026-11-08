"""Prospective synthetic test clocks; no product clock-changing capability."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from alphaquest.forward_comparison import boundary, iso
from alphaquest.forward_reconcile import stamp
from tests.test_forward_comparison import comparison_fixture


def prospective_observation(application, package, *, wall_clock_utc=None):
    """Keep the model dates fixed; choose a later compatible synthetic scope."""
    seal=stamp(application['result']['economic_selection']['sealed_at_utc'])
    wall=stamp(wall_clock_utc) if wall_clock_utc is not None else datetime.now(timezone.utc)
    created=max(seal,wall)+timedelta(seconds=1)
    window=package['outer_window'];origin=date.fromisoformat(window['first_session'])
    horizon=date.fromisoformat(window['cutoff_date_exclusive'])-origin
    first=created.astimezone(ZoneInfo('America/Chicago')).date()
    while first.weekday()!=origin.weekday() or boundary(str(first),str(first+horizon))[0]<=created:
        first+=timedelta(days=1)
    _,_,template,_,_,_=comparison_fixture();plan=deepcopy(template['plan'])
    shift=lambda day:str(first+(date.fromisoformat(day)-origin))
    plan.update(first_session=str(first),cutoff_date_exclusive=str(first+horizon),
        open_sessions=[shift(day) for day in window['sessions']],
        early_closes={shift(day):clock for day,clock in (package.get('native_execution') or {}).get('early_closes',{}).items()
            if window['first_session']<=day<window['cutoff_date_exclusive']})
    return plan,iso(created)


def coverage_events_for_binding(binding, *, complete=False):
    """Re-anchor opening and closing clocks separately, including DST weeks."""
    _,_,old,records,_,_=comparison_fixture()
    old_start,old_end=stamp(old['coverage_start_utc']),stamp(old['coverage_cutoff_utc'])
    start,end=stamp(binding['coverage_start_utc']),stamp(binding['coverage_cutoff_utc'])
    events=[]
    for row in records:
        event=deepcopy(row['event']);when=stamp(event['event_time_utc'])
        if when==old_start:event['event_time_utc']=iso(start)
        else:
            assert old_end-timedelta(hours=1)<=when<=old_end,'Extend the explicit fixture clock mapping for a changed oracle.'
            event['event_time_utc']=iso(end+(when-old_end))
        if event['kind']=='account_coverage':
            event.update(plan_sha256=binding['plan_sha256'],package_sha256=binding['package_sha256'],
                account_id=binding['plan']['account_id'],first_session=binding['plan']['first_session'],
                cutoff_date_exclusive=binding['plan']['cutoff_date_exclusive'],complete_through_utc=iso(end),
                coverage='complete' if complete else 'partial')
        events.append(event)
    return events,iso(end+timedelta(seconds=2))
