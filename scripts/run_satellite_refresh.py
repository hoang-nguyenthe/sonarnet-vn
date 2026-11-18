"""Bounded Vietnam refresh with an explicit source circuit breaker.

Only the existing detector is used. RTC fallback has different radiometric
processing, recorded per tile; integration success is not an accuracy claim.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def read_state(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def still_cooling(until, now):
    if not until:
        return False
    try:
        value = datetime.fromisoformat(until.replace('Z','+00:00'))
        return value.tzinfo is not None and value > now
    except (ValueError, AttributeError):
        return False


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pending.json')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def cooldown_decision(previous, now, force_probe=False):
    return (not force_probe and previous.get('state') in {'blocked', 'error'}
            and still_cooling(previous.get('retry_after'), now))


def status_summary(state):
    return (f"## Vietnam refresh\n\nState: {state['state']}. Source: {state.get('source') or 'not checked'}. "
            f"Updated detail cells: {state.get('updated_this_run',0)}. Failed detail cells: {state.get('failed_this_run',0)}. "
            f"Overview refreshed: {'yes' if state.get('overview_updated') else 'no'}.\n\n"
            "A completed run does not imply new imagery, full coverage or validated detector accuracy.\n")


def write_summary(markdown):
    if summary := os.getenv('GITHUB_STEP_SUMMARY'):
        with open(summary,'a') as out:
            out.write(markdown)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--time-budget-seconds',type=int,default=2700)
    parser.add_argument('--max-updates',type=int,default=0)
    parser.add_argument('--force-probe',action='store_true')
    parser.add_argument('--check-cooldown',action='store_true',
                        help='Report whether a refresh is due; does not load dependencies or modify assets')
    args=parser.parse_args(argv)
    if not 60 <= args.time_budget_seconds <= 3600 or args.max_updates < 0:
        parser.error('Invalid bounded runtime or update limit')
    path=ROOT/'assets/real_scan/refresh_status.json'
    previous=read_state(path)
    now=datetime.now(timezone.utc)
    cooling = cooldown_decision(previous, now, args.force_probe)
    if args.check_cooldown:
        print('deferred' if cooling else 'due')
        if cooling:
            write_summary('## Vietnam refresh deferred\n\nCooldown active; no catalog check, imagery download, or publication was attempted. Cached observations retain their original dates.\n')
        return
    if cooling:
        print('Source cooldown active; no repeated downloads, old evidence unchanged',flush=True)
        write_summary('## Vietnam refresh deferred\n\nCooldown active; no catalog check, imagery download, or publication was attempted. Cached observations retain their original dates.\n')
        return
    state={'checked_at':now.isoformat(),'region':'vietnam', 'execution':'github-actions-cpu',
           'run_url':f"https://github.com/{os.getenv('GITHUB_REPOSITORY','hoang-nguyenthe/sonarnet-vn')}/actions/runs/{os.getenv('GITHUB_RUN_ID','unknown')}",
           'copernicus_retry_after':previous.get('copernicus_retry_after'),
           'copernicus_state':previous.get('copernicus_state','unknown')}
    source='copernicus'
    overview_updated=False
    from sonarnet.data.copernicus import CopernicusError, CopernicusQuotaError
    from sonarnet.data.planetary import PlanetaryAccessError
    from refresh_sentinel_mosaic import main as mosaic
    from refresh_detailed_scan import main as scan
    if not args.force_probe and still_cooling(state.get('copernicus_retry_after'),now):
        source='planetary'
    else:
        try:
            overview = ROOT/'assets/sentinel1_vietnam_latest.json'
            before = read_state(overview).get('refreshed_at')
            mosaic()
            after = read_state(overview).get('refreshed_at')
            overview_updated = bool(after and after != before)
            state.update(copernicus_state='available',copernicus_retry_after=None)
        except CopernicusError as error:
            source='planetary'
            state.update(copernicus_state='quota_exhausted' if isinstance(error,CopernicusQuotaError) else 'unavailable',
                         copernicus_retry_after=(now+timedelta(hours=24)).isoformat())
            print(f'Copernicus: {type(error).__name__}; use RTC source, keep last overview',flush=True)
    scan_args=['--all-pending','--region','vietnam','--time-budget-seconds',str(args.time_budget_seconds),
               '--max-updates',str(args.max_updates),'--device','cpu','--prefetch','1']
    error_type=None
    try:
        try:
            scan(scan_args+['--source',source])
        except CopernicusQuotaError:
            state.update(copernicus_state='quota_exhausted',
                         copernicus_retry_after=(now+timedelta(hours=24)).isoformat())
            # Partial checkpoint is already saved. Avoid starting a second
            # queue with a fresh time budget; RTC begins at the next run.
            raise
    except Exception as error:
        error_type=type(error).__name__
        state.update(state='blocked' if isinstance(error,(CopernicusError,PlanetaryAccessError)) else 'error',
                     reason=error_type, retry_after=(now+timedelta(hours=24)).isoformat())
    else:
        state.update(reason=None,retry_after=None)
    report=read_state(ROOT/'assets/real_scan/report.json')
    progress=report.get('worker_progress',{})
    try:
        if datetime.fromisoformat(progress.get('checked_at','').replace('Z','+00:00')) < now:
            progress={}
    except (ValueError, TypeError):
        progress={}
    if error_type is None:
        state['state'] = ('ready' if progress.get('updated_this_run',0) or overview_updated else 'checked_no_updates')
    state.update(source=source, finished_at=datetime.now(timezone.utc).isoformat(), overview_updated=overview_updated,
                 catalog_checks_this_run=progress.get('catalog_checks_this_run'),
                 updated_this_run=progress.get('updated_this_run',0),
                 failed_this_run=progress.get('failed_this_run',0))
    write_state(path,state)
    write_summary(status_summary(state))
    print(json.dumps(state,ensure_ascii=False))
    if error_type:
        raise SystemExit(f'Refresh stopped safely: {error_type}; checkpoint and published evidence retained')


if __name__ == '__main__':main()
