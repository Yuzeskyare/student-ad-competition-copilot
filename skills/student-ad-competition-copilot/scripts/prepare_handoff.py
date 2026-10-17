"""Create a conservative handoff record without inventing missing evidence."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from review_contract import digest, inside, load, read_contract
from validate_run import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir','manifest','output-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--readiness-input',help='Existing verified rule/citation evidence; preserve it instead of resetting completed work')
    args=parser.parse_args();root=Path(args.run_dir).resolve();manifest=load(inside(root,args.manifest))
    contract,_=read_contract(root,manifest);dest=inside(root,args.output_dir)
    from execution_contract import release_required
    if release_required(root,manifest):
        from execution_contract import verify_artwork_release
        for ref in contract['final_artifacts']:verify_artwork_release(root,manifest,ref)
    if dest.exists():parser.error('Use a new output directory; never overwrite completed evidence')
    readiness=load(Path(__file__).resolve().parents[1]/'references/templates/submission-readiness.template.json')
    readiness.update(run_id=manifest['run_id'],track=manifest['category'],competition=manifest['competition'],method_scope='artwork-delivery')
    readiness['rule_verification']['status']='not-verified-current'
    readiness['rights_clearance']['open_items']=['Verify rights for the actual final assets and fonts.']
    readiness['citations'].update(status='incomplete',open_items=['Verify visible claims and sources.'],rationale=None)
    readiness['aigc']['used']=manifest.get('aigc_used','unknown')
    if readiness['aigc']['used']=='no':readiness['aigc'].update(status='not-applicable',rationale='Current run explicitly declares no generative AI use.')
    readiness['readiness_boundaries']=['Current rules/specifications and external research citations must be verified before artwork delivery.']
    if args.readiness_input:
        supplied=load(inside(root,args.readiness_input))
        if any(supplied.get(k)!=readiness[k] for k in ('run_id','track','competition')):parser.error('Readiness input identity mismatch')
        readiness=supplied
        readiness['method_scope']='artwork-delivery'
    summary=validate(root,inside(root,args.manifest))
    if summary['content_review_status']=='pass':
        readiness['content_quality'].update(status='pass',evidence_path=manifest['review_contract'])
    elif summary['content_review_status']=='fail':
        readiness['content_quality'].update(status='fail',evidence_path=manifest['review_contract'])
    if summary['technical_pass']:
        readiness['technical_validation'].update(status='pass',evidence_path=manifest['artifacts']['technical_validation'])
    dest.mkdir(parents=True)
    path=dest/'submission-readiness.json';path.write_text(json.dumps(readiness,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    handoff=dict(schema_version='1.0.0',run_id=manifest['run_id'],track=manifest['category'],final_artifacts=contract['final_artifacts'],
        readiness={'path':path.relative_to(root).as_posix(),'sha256':digest(path)},platform_disclosure={'status':'pending'},evidence_slots=[],submission_receipt=None)
    from visual_review_contract import image_budget_message
    message=image_budget_message(root,manifest)
    if message:handoff['direction_generation_summary']=message
    from visual_review_contract import delivery_advisories
    notices=delivery_advisories(root,manifest)
    if notices:handoff['visual_advisories']=notices
    from user_decision_contract import delivery_decisions
    decisions=delivery_decisions(root,manifest)
    if decisions:handoff['user_decisions']=decisions
    from core_return_contract import review_state
    invalid=review_state(root,manifest).get('invalid_return_audit',[])
    if invalid:handoff['invalid_core_returns']=invalid
    output=dest/'handoff.json';output.write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    response={'handoff':output.relative_to(root).as_posix(),'submission_ready':False,'human_approval_created':False}
    if message:response['direction_generation_summary']=message
    if notices:response['visual_advisories']=notices
    print(json.dumps(response,ensure_ascii=False))


if __name__=='__main__':main()
