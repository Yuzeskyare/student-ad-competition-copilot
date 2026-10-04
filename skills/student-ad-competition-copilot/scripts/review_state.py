"""Inspect or create immutable review snapshots from current artifacts and real events."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from review_contract import (inside, load, digest, bound_file, read_contract, decisions,
                             final_state, coverage, human_source, concept_evidence_checks)
from current_artwork_contract import validate_current, required
from execution_contract import validate_events


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8')


def reference(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=digest(path))


def append_decision(root, contract, row):
    """Idempotent for the same source/scope; never infer a verdict or scope."""
    decisions(root, dict(contract, decisions=[row]))
    human_source(root, row['source'], row['quote'])
    source = load(bound_file(root, row['source']))
    scope = coverage(root, row['reviewed_artifacts'])
    for previous in contract['decisions']:
        old = load(bound_file(root, previous['source']))
        if old['event_id'] != source['event_id']:
            continue
        if old != source:
            raise ValueError('Same source event ID has conflicting content; reconcile original evidence')
        if coverage(root, previous['reviewed_artifacts']) & scope:
            if (previous['stage'] == row['stage'] and previous['decision'] == row['decision']
                    and coverage(root, previous['reviewed_artifacts']) == scope
                    and previous.get('production_request_sha256') == row.get('production_request_sha256')
                    and previous['quote'] == row['quote']):
                return previous['id'], False
            # One event may authorize distinct concrete requests. Other overlapping
            # projections need explicit reconciliation, not another user approval.
            different_requests = (previous.get('production_request_sha256') and row.get('production_request_sha256')
                                  and previous['production_request_sha256'] != row['production_request_sha256'])
            if not different_requests:
                raise ValueError('Overlapping projections of one human event; reconcile stages/scope without inventing time or requesting repeated approval')
    candidate = copy.deepcopy(contract)
    candidate['decisions'].append(row)
    decisions(root, candidate)
    contract['decisions'] = candidate['decisions']
    return row['id'], True


def prepare_event(root, contract, payload):
    matches = [r for r in contract['production_requests'] if load(bound_file(root,r))['id'] == payload['request_id']]
    if len(matches) != 1:
        raise ValueError('Select one actual production request ID')
    request = matches[0]
    evidence = load(bound_file(root, payload['evidence']))
    for name in ('call_id','state','occurred_at'):
        if not evidence.get(name):
            raise ValueError('Host evidence needs '+name+'; missing data must not be invented')
    event = {name:evidence[name] for name in ('call_id','state','occurred_at')}
    event.update(request_id=payload['request_id'],request_sha256=request['sha256'],evidence=payload['evidence'])
    prior = None
    for ref in contract.get('production_events',[]):
        value=load(bound_file(root,ref))
        if value['request_sha256']==request['sha256']:
            prior=ref
            if value['evidence']==payload['evidence']:
                validate_events(root,contract)
                return value, ref, False
    if prior: event['previous']=prior
    if evidence['state']=='saved': event['outputs']=evidence.get('outputs')
    return event,None,True


def snapshot(root, manifest, action, payload, destination):
    root=root.resolve()
    contract,rows=read_contract(root,manifest)
    contract=copy.deepcopy(contract); result_manifest=copy.deepcopy(manifest)
    target=inside(root,destination)
    if target.exists(): raise ValueError('Use a new snapshot directory; previous records are immutable')
    staged={}; added=True
    def add(name, value):
        data=encoded(value);path=target/name
        staged[path]=data
        return dict(path=path.relative_to(root).as_posix(),sha256=hashlib.sha256(data).hexdigest())
    if action=='event':
        event,existing,added=prepare_event(root,contract,payload)
        if added:
            ref=add('production-event.json',event)
            validate_events(root,contract,pending=(ref,event))
            contract.setdefault('production_events',[]).append(ref)
    elif action=='decision':
        _,added=append_decision(root,contract,payload)
    elif action=='project':
        if result_manifest.get('category')!='print-ad' or not required(result_manifest,contract,root):
            raise ValueError('Project requires a bound current print set; legacy records do not inherit new source checks')
        if payload:
            if set(payload)-{'final_artifacts','series_plan'}:
                raise ValueError('Project accepts final_artifacts and series_plan only; scope/verdict is not inferred')
            if 'final_artifacts' in payload:contract['final_artifacts']=payload['final_artifacts']
            if 'series_plan' in payload:result_manifest['series_plan']=payload['series_plan']
        validate_current(root,result_manifest,contract)
    else: raise ValueError('Unknown snapshot action')
    if not added:
        return dict(status='already-recorded',manifest_changed=False,approval_granted=False)
    rows=decisions(root,contract)
    refs=contract['final_artifacts']
    state,ids=final_state(root,refs,rows) if refs else ('pending',set())
    contract['content_status']=state
    result_manifest['review_contract']=add('review-contract.json',contract)['path']
    artifacts=result_manifest.setdefault('artifacts',{})
    status=load(inside(root,artifacts['run_status'])) if artifacts.get('run_status') else {}
    status.update(content_review_status=state,review_decision_ids=sorted(ids))
    # Overall gate/delivery status is deliberately not promoted by this helper.
    artifacts['run_status']=add('run-status.json',status)['path']
    if action=='project':
        status.update(status='in-progress',delivery_complete=False)
        # Replace the staged status bytes before the final commit; old technical
        # or overall completion cannot certify a newly projected collection.
        if 'technical_validation_status' in status:status['technical_validation_status']='not-run'
        add('run-status.json',status)
        delivery=load(inside(root,artifacts['delivery_manifest'])) if artifacts.get('delivery_manifest') else {}
        delivery['final_artifacts']=refs
        delivery.update(content_status=state,delivery_complete=False)
        if 'status' in delivery:delivery['status']='in-progress'
        # Legacy alias is a derived copy only when it already exists.
        if 'artworks' in delivery:delivery['artworks']=refs
        artifacts['delivery_manifest']=add('delivery-manifest.json',delivery)['path']
        technical=[]
        for index, ref in enumerate(refs,1):
            source=bound_file(root,ref)
            copied=target/'technical-inputs'/f'{index:03}{source.suffix.lower()}'
            data=source.read_bytes()
            if hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('Current artwork changed during projection')
            staged[copied]=data
            technical.append(dict(source=ref,copy=dict(path=copied.relative_to(root).as_posix(),sha256=ref['sha256'])))
        add('current-index.json',dict(final_artifacts=refs,content_status=state,review_decision_ids=sorted(ids),technical_inputs=technical,
                                      visual_quality_certified=False,delivery_completion_inferred=False))
    add('snapshot-inputs.json',dict(action=action,manifest=manifest,payload=payload))
    # Commit marker is written last. Failed writes leave an uncommitted directory,
    # while the caller's manifest and all previous artifacts remain untouched.
    target.mkdir(parents=True,exist_ok=False)
    for path,data in staged.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
    committed=target/'manifest.json'
    with committed.open('xb') as stream:stream.write(encoded(result_manifest))
    return dict(status='snapshot-created',manifest=reference(root,committed),content_status=state,
                ancillary_checks=concept_evidence_checks(root,result_manifest),
                members=len(refs),approval_granted=False,run_scope=result_manifest['run_scope'],
                next_action='Use this manifest for subsequent work; run existing quality and visual checks. The snapshot is not a delivery pass.')


def inspect_current(root,manifest):
    contract,rows=read_contract(root,manifest)
    if manifest.get('category')!='print-ad' or not required(manifest,contract,root):
        raise ValueError('Inspect requires a bound current print set; historical records have not passed these checks')
    results=validate_current(root,manifest,contract)
    states=validate_events(root,contract)
    ancillary=concept_evidence_checks(root,manifest)
    return dict(status='checked-with-warnings' if any(not r['passed'] for r in ancillary) else 'checked',
                ancillary_checks=ancillary,results=[dict(unit=r['unit'],native=r['native'],render=r['render']) for r in results],
                members=len(results),production_states={k:v['state'] for k,v in states.items()},
                visual_quality_certified=False)


def main():
    import sys
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True,type=Path)
    p.add_argument('--manifest',required=True,help='Run-relative manifest')
    p.add_argument('--action',required=True,choices=['inspect','project','event','decision'])
    p.add_argument('--payload',help='Run-relative JSON; event: {request_id,evidence}; decision: exact existing-contract row; project: optional {final_artifacts,series_plan}')
    p.add_argument('--destination',help='New run-relative snapshot directory; manifest.json is the commit marker')
    args=p.parse_args()
    try:
        root=args.run_dir.resolve();manifest=load(inside(root,args.manifest))
        if args.action=='inspect':result=inspect_current(root,manifest)
        else:
            if not args.destination or (args.action!='project' and not args.payload):raise ValueError('Snapshot needs destination and action payload')
            payload=load(inside(root,args.payload)) if args.payload else {}
            result=snapshot(root,manifest,args.action,payload,args.destination)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        print(json.dumps(dict(status='failed',reason=str(exc)),ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
