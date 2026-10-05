"""Unified read-only validation and recovery receipt for all three tracks."""
import argparse
import importlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from review_contract import bound_file, coverage, final_state, inside, load, read_contract
from validate_submission_readiness import validate as validate_readiness
from quality_gate_contract import check_summary

TRACKS={'print-ad','ad-copy','marketing-plan'}


def required_content_checks(manifest):
    required=set()
    if manifest.get('schema_version')=='0.4.0':
        if manifest.get('category') in {'print-ad','marketing-plan'} and manifest.get('run_scope')!='concept-only':
            required.add('final-pixel-evidence')
        if manifest.get('category') in {'ad-copy','marketing-plan'} and (manifest.get('award_review_requested') is True or manifest.get('revision_mode')=='challenge'):
            required.add('creative-iteration-evidence')
    return required


def repair_before_review(run_result):
    """Separate observed failures from the unfinished final human decision."""
    checks={r['name']:r for r in run_result.get('checks',[])}
    repairs=[]
    for name in run_result.get('failure_names',[]):
        row=checks.get(name,{})
        evidence=row.get('evidence')
        waiting=row.get('state') == 'in-progress'
        if not waiting and row.get('severity')!='reminder':repairs.append(name)
    return repairs


def technical_diagnostics(root, manifest, contract):
    """Explain print report binding without changing acceptance or approvals."""
    if manifest.get('category') != 'print-ad':
        return []
    try:
        report_path = inside(root, manifest['artifacts']['technical_validation'])
        report = load(report_path)
        expected = {(str(inside(root, r['path'])), r['sha256']) for r in contract['final_artifacts']}
        actual = {(str(Path(r['path']).resolve()), r['sha256']) for r in report['files']}
        result = []
        if not expected:
            result.append({'code': 'empty-current-artifacts'})
        if expected != actual:
            result.append({'code': 'technical-artifact-binding-mismatch',
                'expected_only': [dict(path=p, sha256=h) for p,h in sorted(expected-actual)],
                'reported_only': [dict(path=p, sha256=h) for p,h in sorted(actual-expected)]})
        if report.get('technical_validation_status') != 'pass' or report.get('failure_names'):
            result.append({'code': 'file-profile-not-passed', 'status': report.get('technical_validation_status'),
                           'failure_names': report.get('failure_names', [])})
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [{'code': 'technical-report-unavailable-or-invalid', 'reason': str(exc)}]


def technical_state(root,manifest,run_result,contract):
    checks={r['name']:r['passed'] for r in run_result.get('checks',[])}
    if manifest['category']=='ad-copy':
        return checks.get('technical-pass',False) and checks.get('technical-final-hash-linked',False)
    if manifest['category']=='marketing-plan':return checks.get('technical-validation-linked',False)
    try:
        report=load(inside(root,manifest['artifacts']['technical_validation']))
        expected={(str(inside(root,r['path'])),r['sha256']) for r in contract['final_artifacts']}
        actual={(str(Path(r['path']).resolve()),r['sha256']) for r in report['files']}
        return bool(expected) and expected==actual and report.get('technical_validation_status')=='pass' and not report.get('failure_names')
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return False


def inspect_handoff(root,manifest,contract,content,technical,path):
    handoff=load(inside(root,path))
    if handoff.get('run_id')!=manifest['run_id'] or handoff.get('track')!=manifest['category'] or handoff.get('schema_version')!='1.0.0':
        raise ValueError('Handoff identity mismatch')
    expected=coverage(root,contract['final_artifacts'])
    if coverage(root,handoff['final_artifacts'])!=expected:raise ValueError('Handoff artifacts differ from current reviewed files')
    readiness=load(bound_file(root,handoff['readiness']))
    if any(readiness.get(k)!=v for k,v in {'run_id':manifest['run_id'],'track':manifest['category'],'competition':manifest['competition']}.items()):
        raise ValueError('Readiness identity differs from this run')
    result=validate_readiness(readiness,root)
    if result['status']!='passed':raise ValueError('Invalid readiness record: '+', '.join(result['failure_names']))
    declared=readiness['content_quality']['status']
    if (declared=='pass') != (content=='pass'):raise ValueError('Readiness content status conflicts with current decisions')
    if (readiness['technical_validation']['status']=='pass') != bool(technical):raise ValueError('Readiness technical status is stale or unbound')
    delivery_mode=readiness.get('method_scope')=='artwork-delivery'
    disclosure=handoff.get('platform_disclosure',{'status':'pending'})
    if delivery_mode:
        # This compatibility field is informational; it cannot gate artwork delivery.
        value=disclosure.get('status') if isinstance(disclosure,dict) else None
        disclosure={'status':value if isinstance(value,str) and value in {'pending','complete','not-required'} else 'unknown'}
    elif not isinstance(disclosure,dict):raise ValueError('Platform disclosure must be an object')
    if not delivery_mode and disclosure.get('status') not in {'pending','complete','not-required'}:raise ValueError('Unknown platform disclosure state')
    if not delivery_mode and disclosure['status'] in {'complete','not-required'}:
        bound_file(root,disclosure['rule_evidence'])
        if not disclosure.get('rule_quote'):raise ValueError('Platform disclosure needs current rule basis')
        if disclosure['status']=='complete':bound_file(root,disclosure['submitted_evidence'])
    slots=handoff['evidence_slots'];seen=set();open_slots=[]
    if not isinstance(slots,list):raise ValueError('Evidence slots must be a list')
    units={key[3] for key in expected}
    for slot in slots:
        if not slot.get('id') or slot['id'] in seen:raise ValueError('Evidence slot IDs must be unique')
        seen.add(slot['id'])
        if not isinstance(slot.get('affected_units'),list) or not slot['affected_units'] or not set(slot['affected_units'])<=units:raise ValueError('Evidence slot must identify affected current pages/artworks')
        if slot.get('status')=='hypothesis':
            if not all(slot.get(k) for k in ('hypothesis','frontstage_label','reversal_trigger','required_before')):
                raise ValueError('Provisional evidence needs a visible hypothesis label, reversal trigger and fill deadline')
            if slot['required_before'] not in {'submission','claim-finalization','real-execution'}:
                raise ValueError('Evidence deadline must be submission, claim-finalization or real-execution')
            open_slots.append(slot['id'])
        elif slot.get('status')=='verified':
            bound_file(root,slot['evidence'])
            if slot.get('provenance') not in {'real-first-party','public-source'}:raise ValueError('Simulations cannot verify a real evidence slot')
        elif slot.get('status')=='not-applicable':
            if not slot.get('rationale'):raise ValueError('Excluded evidence needs a rationale')
        else:raise ValueError('Unknown evidence slot state')
    ready=result['submission_ready']
    if ready:
        if content!='pass' or not technical or disclosure['status']=='pending':raise ValueError('Submission is not ready while current content/technical/disclosure remains open')
        if any(s['status']=='hypothesis' and s['required_before'] in {'submission','claim-finalization'} for s in slots):
            raise ValueError('Required research/feasibility evidence remains provisional')
        receipt=load(bound_file(root,handoff['submission_receipt']))
        if receipt.get('run_id')!=manifest['run_id'] or coverage(root,receipt['uploaded_artifacts'])!=expected:
            raise ValueError('Upload receipt belongs to different files or run')
        evidence=bound_file(root,receipt['platform_evidence'])
        if evidence!=inside(root,readiness['submission']['receipt_path']):raise ValueError('Receipt sources disagree')
    return dict(submission_ready=ready,delivery_ready=result['delivery_ready'],delivery_blockers=result['delivery_blockers'],post_delivery_reminders=result['post_delivery_reminders'],open_evidence_slots=open_slots,
        blocking_evidence_slots=[s['id'] for s in slots if s['status']=='hypothesis' and s['required_before']=='claim-finalization'],
        platform_disclosure=disclosure['status'],readiness=result)


def validate(root,manifest_path,handoff_path=None):
    root=root.resolve();manifest=load(manifest_path)
    track=manifest.get('category')
    if track not in TRACKS:raise ValueError('Unknown track; do not route to an approximate validator')
    module=importlib.import_module('validate_'+track.replace('-','_')+'_run')
    run_result=module.validate(root,manifest_path)
    errors=[];contract={};content='pending';current=False
    try:
        contract,rows=read_contract(root,manifest)
        if contract['final_artifacts']:content,_=final_state(root,contract['final_artifacts'],rows)
        current=run_result.get('review_contract_status')=='verified'
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:errors.append(str(exc))
    technical=technical_state(root,manifest,run_result,contract)
    handoff=None
    if handoff_path:
        try:handoff=inspect_handoff(root,manifest,contract,content if current else 'unverified',technical,handoff_path)
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:errors.append(str(exc))
    required=required_content_checks(manifest)
    content_checks=[r for r in run_result.get('checks',[]) if r['name'] in required]
    missing=required-{r['name'] for r in content_checks}
    if missing:errors.append('Missing required content checks: '+', '.join(sorted(missing)))
    classified = check_summary(run_result.get('checks', []))
    repairs = repair_before_review(run_result)
    if run_result.get('errors'):
        errors.extend(run_result['errors'])
    passed=run_result.get('status')=='passed' and not errors and current
    content_pass=content=='pass' and current and not missing and all(r['passed'] is True for r in content_checks)
    submission_ready=bool(passed and content_pass and technical and handoff and handoff['submission_ready'])
    delivery_complete=bool(passed and content_pass and technical and manifest.get('run_scope')=='delivery-candidate' and handoff and handoff['delivery_ready'] and not handoff['blocking_evidence_slots'])
    method=False
    try:
        status=load(inside(root,manifest['artifacts']['run_status']))
        method=bool(passed and (manifest.get('method_validation_status')=='method-validated' or status.get('method_run_complete') is True))
    except (OSError,ValueError,KeyError,TypeError):pass
    if manifest.get('schema_version')!='0.4.0':next_action='Preserve legacy results; explicitly migrate evidence before claiming current-contract acceptance.'
    elif errors:next_action='Repair the first evidence/identity error: '+errors[0]
    elif not current:next_action='Repair the current review contract before reusing or requesting a human decision.'
    elif content=='fail':next_action='Return to the layer identified by the current human rejection.'
    elif repairs:next_action='Repair the first failed run check: '+repairs[0]
    elif content=='pending' and manifest.get('run_scope')=='delivery-candidate' and not technical:next_action='Repair final-file technical validation before human review.'
    elif content=='pending' and any(r['kind']=='work' for r in classified['waiting_details']):next_action='Complete unfinished stage checks without remaking approved work: '+next(r['name'] for r in classified['waiting_details'] if r['kind']=='work')
    elif content=='pending' and manifest.get('run_scope')=='delivery-candidate':next_action='Present current final objects for one scoped human content decision; reuse any existing valid decision.'
    elif classified['waiting_checks']:next_action='Complete unfinished stage checks without remaking approved work: '+classified['waiting_checks'][0]
    elif manifest.get('run_scope')=='concept-only':next_action='None for the completed concept scope; enter production only if the requested target includes it.'
    elif manifest.get('run_scope')=='production-candidate':next_action='Review the completed production scope before the next requested delivery stage.'
    elif not handoff:next_action='Record current competition rules, final specifications and completed external citations for artwork delivery.'
    elif handoff['blocking_evidence_slots']:next_action='Fill the next applicable evidence slot: '+handoff['blocking_evidence_slots'][0]
    elif not delivery_complete:next_action='Complete the artwork delivery requirement: '+', '.join(handoff['delivery_blockers'])
    else:next_action='None: artwork delivery is complete. Rights and AIGC/platform matters are post-delivery reminders only.'
    state = 'failed' if errors or not current or repairs or content == 'fail' else ('passed' if passed else 'in-progress')
    return dict(schema_version='1.1.0',run_id=manifest['run_id'],track=track,status=state,
        repair_checks=repairs,waiting_checks=classified['waiting_checks'],waiting_details=classified['waiting_details'],
        technical_diagnostics=technical_diagnostics(root,manifest,contract),
        technical_pass=bool(technical),content_pass=content_pass,content_review_status=content if current else 'unverified',
        method_validated=method,delivery_complete=delivery_complete,post_delivery_reminders=handoff['post_delivery_reminders'] if handoff else [],submission_ready=submission_ready,review_contract_status=run_result.get('review_contract_status'),
        run_validation=run_result,handoff=handoff,errors=errors,next_action=next_action)


def validate_index(root, index_path):
    """Resolve explicitly declared direction scopes; never infer them from root prose."""
    root = root.resolve()
    index = load(index_path)
    if index.get('schema_version') != '1.0.0' or not isinstance(index.get('directions'), list) or not index['directions']:
        raise ValueError('Direction index needs a version and nonempty directions')
    ids = [row.get('id') for row in index['directions']]
    targets = index.get('target_directions')
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids) or not isinstance(targets, list) or len(targets) != len(ids) or set(targets) != set(ids):
        raise ValueError('Index targets must identify every unique direction exactly once')
    results = []
    for direction in index['directions']:
        manifest_path = inside(root, direction['manifest'])
        manifest = load(manifest_path)
        if manifest.get('run_id') != index.get('run_id') or manifest.get('selected_direction') != direction['id']:
            raise ValueError('Direction identity differs from its manifest')
        result = validate(root, manifest_path, direction.get('handoff'))
        results.append(dict(direction_id=direction['id'], manifest=direction['manifest'], **result))
    failed = [r for r in results if r['status'] == 'failed']
    unfinished = [r for r in results if not r['delivery_complete']]
    chosen = (failed or unfinished or results)[0]
    complete = not unfinished
    return dict(schema_version='1.1.0', scope='multi-direction', run_id=index['run_id'],
                status='failed' if failed else ('passed' if complete else 'in-progress'),
                technical_pass=all(r['technical_pass'] for r in results), content_pass=all(r['content_pass'] for r in results),
                method_validated=all(r['method_validated'] for r in results), delivery_complete=complete,
                submission_ready=all(r['submission_ready'] for r in results), directions=results,
                next_action='None: every declared direction has completed artwork delivery.' if complete else chosen['direction_id']+': '+chosen['next_action'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, help='Root directory of this run')
    scope = parser.add_mutually_exclusive_group(required=True)
    for name in ('manifest','index'):scope.add_argument('--'+name,help='Path relative to --run-dir; must stay inside the run')
    parser.add_argument('--output', required=True, help='New receipt relative to --run-dir; must stay inside the run')
    parser.add_argument('--handoff');args=parser.parse_args();root=Path(args.run_dir).resolve()
    if args.index and args.handoff:parser.error('--handoff belongs to one manifest; declare handoffs inside a direction index')
    result=validate_index(root,inside(root,args.index)) if args.index else validate(root,inside(root,args.manifest),args.handoff)
    out=inside(root,args.output)
    if out.exists():parser.error('Use a new output receipt; do not overwrite historical evidence')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','technical_pass','content_pass','method_validated','delivery_complete','submission_ready','next_action')},ensure_ascii=False))
    return {'passed': 0, 'in-progress': 2}.get(result['status'], 1)


if __name__=='__main__':raise SystemExit(main())
