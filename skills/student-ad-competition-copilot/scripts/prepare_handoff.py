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
    args=parser.parse_args();root=Path(args.run_dir).resolve();manifest=load(inside(root,args.manifest))
    contract,_=read_contract(root,manifest);dest=inside(root,args.output_dir)
    if dest.exists():parser.error('Use a new output directory; never overwrite completed evidence')
    readiness=load(Path(__file__).resolve().parents[1]/'references/templates/submission-readiness.template.json')
    readiness.update(run_id=manifest['run_id'],track=manifest['category'],competition=manifest['competition'],method_scope='real-submission')
    readiness['rule_verification']['status']='not-verified-current'
    readiness['rights_clearance']['open_items']=['Verify rights for the actual final assets and fonts.']
    readiness['citations'].update(status='incomplete',open_items=['Verify visible claims and sources.'],rationale=None)
    readiness['aigc']['used']=manifest.get('aigc_used','unknown')
    if readiness['aigc']['used']=='no':readiness['aigc'].update(status='not-applicable',rationale='Current run explicitly declares no generative AI use.')
    readiness['readiness_boundaries']=['Current rules, rights, platform disclosure, registration and upload receipt remain to be verified.']
    summary=validate(root,inside(root,args.manifest))
    if summary['content_pass']:
        readiness['content_quality'].update(status='pass',evidence_path=manifest['review_contract'])
    elif summary['content_review_status']=='fail':
        readiness['content_quality'].update(status='fail',evidence_path=manifest['review_contract'])
    if summary['technical_pass']:
        readiness['technical_validation'].update(status='pass',evidence_path=manifest['artifacts']['technical_validation'])
    dest.mkdir(parents=True)
    path=dest/'submission-readiness.json';path.write_text(json.dumps(readiness,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    handoff=dict(schema_version='1.0.0',run_id=manifest['run_id'],track=manifest['category'],final_artifacts=contract['final_artifacts'],
        readiness={'path':path.relative_to(root).as_posix(),'sha256':digest(path)},platform_disclosure={'status':'pending'},evidence_slots=[],submission_receipt=None)
    output=dest/'handoff.json';output.write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'handoff':output.relative_to(root).as_posix(),'submission_ready':False,'human_approval_created':False}))


if __name__=='__main__':main()
