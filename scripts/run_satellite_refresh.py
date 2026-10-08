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
from sonarnet.data.copernicus import CopernicusError, CopernicusQuotaError
from sonarnet.data.planetary import PlanetaryAccessError


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--time-budget-seconds',type=int,default=2700)
    parser.add_argument('--max-updates',type=int,default=0)
    parser.add_argument('--force-probe',action='store_true')
    args=parser.parse_args(argv)
    if not 60 <= args.time_budget_seconds <= 3600 or args.max_updates < 0:
        parser.error('Invalid bounded runtime or update limit')
    path=ROOT/'assets/real_scan/refresh_status.json'
    previous=read_state(path)
    now=datetime.now(timezone.utc)
    if not args.force_probe and previous.get('state') == 'blocked' and still_cooling(previous.get('retry_after'),now):
        print('Source cooldown active; no repeated downloads, old evidence unchanged')
        return
    state={'checked_at':now.isoformat(),'region':'vietnam', 'execution':'github-actions-cpu',
           'run_url':f"https://github.com/{os.getenv('GITHUB_REPOSITORY','hoang-nguyenthe/sonarnet-vn')}/actions/runs/{os.getenv('GITHUB_RUN_ID','unknown')}",
           'copernicus_retry_after':previous.get('copernicus_retry_after'),
           'copernicus_state':previous.get('copernicus_state','unknown')}
    source='copernicus'
    from refresh_sentinel_mosaic import main as mosaic
    from refresh_detailed_scan import main as scan
    if not args.force_probe and still_cooling(state.get('copernicus_retry_after'),now):
        source='planetary'
    else:
        try:
            mosaic()
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
        state.update(state='ready',reason=None,retry_after=None)
    report=read_state(ROOT/'assets/real_scan/report.json')
    progress=report.get('worker_progress',{})
    try:
        if datetime.fromisoformat(progress.get('checked_at','').replace('Z','+00:00')) < now:
            progress={}
    except (ValueError, TypeError):
        progress={}
    state.update(source=source, finished_at=datetime.now(timezone.utc).isoformat(),
                 updated_this_run=progress.get('updated_this_run',0),
                 failed_this_run=progress.get('failed_this_run',0))
    write_state(path,state)
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as out:
            out.write(f"## Vietnam refresh\n\nState: {state['state']}. Source: {source}. "
                      f"Updated cells: {state['updated_this_run']}. Failed cells: {state['failed_this_run']}.\n\n"
                      "A completed run does not imply full coverage or validated detector accuracy.\n")
    print(json.dumps(state,ensure_ascii=False))
    if error_type:
        raise SystemExit(f'Refresh stopped safely: {error_type}; checkpoint and published evidence retained')


if __name__ == '__main__':main()
