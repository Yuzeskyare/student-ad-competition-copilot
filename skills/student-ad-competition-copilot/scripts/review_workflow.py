"""Native review preparation, host-metadata capture, binding and immutable admission."""
import argparse
import copy
import json
import uuid
from pathlib import Path
from review_contract import inside, load, bound_file, digest, timestamp
from review_projection import project, ref, write_once
from workflow_runtime import now, save, timing, timing_summary, update_status, receipt, check_entries


def error(field, value, source):
    raise ValueError(f'field={field} current={value!r}; legal source={source}')


def allocate(root, stage):
    path=inside(root,'05-review/workflow/'+stage+'-'+uuid.uuid4().hex)
    path.mkdir(parents=True,exist_ok=False)
    return path


def write(root, path, value, raw=False):
    data=value.encode('utf-8') if raw else (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    write_once(path,data)
    return ref(root,path)


def prepare(root, row, author_session_id):
    """Use a saved current render; generate views with prepare_visual_views first."""
    from validate_print_ad_run import INDEPENDENT_BLIND_RUBRIC_V6, blind_input_digest
    path=allocate(root,'blind');row=copy.deepcopy(row)
    row['id']='review-'+uuid.uuid4().hex
    row.pop('user_confirmations',None)
    row.pop('rework',None)
    render=load(bound_file(root,row['render_record']))
    native=[v['file'] for v in render['views'] if v['scale']=='native']
    if native!=[row['observed_image']]:error('observed_image',row.get('observed_image'),'current render_record native view')
    bound_file(root,row['observed_image'])
    inputs=[dict(role='artwork',file=row['observed_image'])]
    state=dict(stage='blind-ready',row=row,author_session_id=author_session_id,input_prepared_at=now(),
               inputs=inputs,input_manifest_sha256=blind_input_digest(inputs),
               request=write(root,path/'request.txt',INDEPENDENT_BLIND_RUBRIC_V6,True))
    write(root,path/'state.json',state)
    return dict(state=ref(root,path/'state.json'),inputs=inputs,request=state['request'],image_generation_calls=0)


def host_record(root, host_ref, state, rubric):
    """Capture actual exported host metadata; never substitute local observation time."""
    host=load(bound_file(root,host_ref))
    fields={'checker_context','author_session_id','checker_session_id','invocation_id','started_at','completed_at','raw_return'}
    if set(host)!=fields:error('host',list(host),'actual exported host event with '+str(sorted(fields)))
    if host['author_session_id']!=state['author_session_id'] or host['checker_context']!='fresh-isolated':
        error('host.context',host,'fresh isolated invocation belonging to this author')
    if not host['checker_session_id'] or not host['invocation_id'] or host['checker_session_id']==host['author_session_id']:
        error('host.identifiers',host,'actual independent host session/call identifiers')
    if not timestamp(state['input_prepared_at'])<=timestamp(host['started_at'])<=timestamp(host['completed_at'])<=timestamp(now()):
        error('host.started_at',host['started_at'],'actual host dispatch after input_prepared_at='+state['input_prepared_at'])
    bound_file(root,host['raw_return'])
    return dict(rubric_version=rubric,**host,unavailable_metadata={},inputs=state['inputs'],request=state['request'])


def capture_blind(root, state_ref, host_ref):
    state=load(bound_file(root,state_ref))
    if state['stage']!='blind-ready':error('stage',state['stage'],'blind-ready state')
    path=allocate(root,'compare');row=state['row']
    record=host_record(root,host_ref,state,'print-core-blind-v6')
    record.update(input_prepared_at=state['input_prepared_at'],saved_at=now(),input_manifest_sha256=state['input_manifest_sha256'])
    blind=write(root,path/'blind.json',record)
    for p in row.get('product_triptychs',[]):
        p['triptych']=project(root,p['triptych'],p['element_id'],(path/(uuid.uuid4().hex+'-projection.json')).relative_to(root).as_posix())
    from validate_print_ad_run import current_comparison_request
    lock=dict(statement=row['core_action'],statement_sha256=row['core_claim_sha256'])
    inputs=[dict(role=k,file=v) for k,v in [('artwork',row['observed_image']),('official-product-asset',row['official_product_asset']),
            ('core-action',write(root,path/'claim.txt',row['core_action'],True)),
            ('thumbnail',next(v['file'] for v in load(bound_file(root,row['render_record']))['views'] if v['scale']=='thumbnail')),
            ('proposition-message',row['proposition_message'])]]
    inputs += [dict(role='product-triptych:'+p['element_id'],file=load(bound_file(root,p['triptych']))['image']) for p in row.get('product_triptychs',[])]
    inputs += [dict(role='product-triptych-metadata:'+p['element_id'],file=p['triptych']) for p in row.get('product_triptychs',[])]
    inputs.append(dict(role='blind-read',file=record['raw_return']))
    inputs += [dict(role='mandatory-brand-asset:'+p['element_id'],file=p['official']) for p in row['required_brand_assets']]
    state=dict(stage='compare-ready',row=row,author_session_id=state['author_session_id'],blind_read=blind,
               input_prepared_at=now(),inputs=inputs,request=write(root,path/'request.txt',current_comparison_request(root,row,blind,lock),True))
    write(root,path/'host-source.json',host_ref)
    write(root,path/'state.json',state)
    return dict(state=ref(root,path/'state.json'),inputs=inputs,request=state['request'])


def bind_return(root, raw_ref, row, blind):
    """Bind only transport identifiers; preserve every independent judgment byte-for-byte."""
    raw=load(bound_file(root,raw_ref));bound=copy.deepcopy(raw)
    def set_binding(obj,key,value):
        if key in obj and obj[key]!=value:error(key,obj[key],'fixed request binding '+repr(value))
        obj[key]=value
    set_binding(bound,'blind_read_sha256',blind['sha256'])
    set_binding(bound,'core_claim_sha256',row['core_claim_sha256'])
    for answer in bound.get('answers',{}).values():set_binding(answer,'blind_read_sha256',blind['sha256'])
    products={p['element_id']:p for p in row.get('product_triptychs',[])}
    for item in bound.get('comparison',{}).get('product_scene',[]):
        if item.get('element_id') not in products:error('product_scene.element_id',item.get('element_id'),'fixed request product element_ids')
        for key in ('role','triptych'):set_binding(item,key,products[item['element_id']][key])
    return bound


def capture_compare(root, state_ref, host_ref, manifest):
    state=load(bound_file(root,state_ref))
    if state['stage']!='compare-ready':error('stage',state['stage'],'compare-ready state')
    path=allocate(root,'admit');row=state['row'];record=host_record(root,host_ref,state,'print-core-product-v8')
    raw=bind_return(root,record['raw_return'],row,state['blind_read'])
    original=record['raw_return'];record['raw_return']=write(root,path/'bound-return.json',raw)
    write(root,path/'return-binding.json',dict(original=original,bound=record['raw_return'],host=host_ref,
          fields='transport hashes and exact product triptych bindings only; answers/observations unchanged'))
    record.update(blind_read=state['blind_read'],core_claim_sha256=row['core_claim_sha256'])
    row.update(answers=raw['answers'],independent_check=write(root,path/'compare.json',record),checked_at=now())
    from core_return_contract import validate_return
    validate_return(root,manifest,row)
    review=copy.deepcopy(manifest['core_creative_review'])
    same=[r for r in review['assessments'] if r['observed_image']['sha256']==row['observed_image']['sha256']]
    if same:
        pending=[e for e in review.get('invalid_returns',[]) if e['assessment_id'] in {r['id'] for r in same} and e['replacement_assessment_id'] is None]
        if len(pending)!=1:error('same-artwork',row['observed_image'],'one native pending invalid-return registration; valid adverse returns cannot be silently superseded')
        from core_return_contract import update_review
        review=update_review(root,manifest,'replace-core-return',dict(assessment_id=pending[0]['assessment_id'],replacement=row))
    else:
        review['assessments'].append(row)
        previous={r['id']:r for r in review['assessments']}
        review['current_assessment_ids']=[i for i in review.get('current_assessment_ids',[]) if previous[i]['artifact']['path']!=row['artifact']['path']]+[row['id']]
    result=copy.deepcopy(manifest);result['core_creative_review']=review
    write(root,path/'manifest.json',result)
    return dict(manifest=ref(root,path/'manifest.json'),assessment_id=row['id'],original_return=original)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True,type=Path)
    p.add_argument('--action',required=True,choices=['prepare','blind-save','compare-save','status','receipt','check-entry','timing-start','timing-end','timing-summary'])
    p.add_argument('--payload',help='Run-relative JSON containing actual references; see native-review-workflow.md')
    args=p.parse_args();root=args.run_dir.resolve()
    payload=load(inside(root,args.payload)) if args.payload else {}
    token=None
    try:
        if args.action not in {'timing-start','timing-end','timing-summary'}:token=timing(root,args.action,'start')['token']
        if args.action=='prepare':result=prepare(root,payload['row'],payload['author_session_id'])
        elif args.action=='blind-save':result=capture_blind(root,payload['state'],payload['host'])
        elif args.action=='compare-save':result=capture_compare(root,payload['state'],payload['host'],load(bound_file(root,payload['manifest'])))
        elif args.action=='status':result=update_status(root,load(bound_file(root,payload['manifest'])),payload['member'],payload['changes'])
        elif args.action=='receipt':result=receipt(root,**payload)
        elif args.action=='check-entry':result=check_entries(root)
        elif args.action=='timing-summary':result=timing_summary(root)
        else:result=timing(root,payload['stage'],'start' if args.action=='timing-start' else 'end',payload.get('token'),payload.get('outcome'),payload.get('recovery_of'))
        if token:timing(root,args.action,'end',token,'passed')
        print(json.dumps(dict(status='ok',result=result),ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:
        if token:timing(root,args.action,'end',token,'failed')
        print(json.dumps(dict(status='failed',reason=str(exc),recovery_token=token,
             source='payload field paths must come from the previous command or original host event; use --help and native-review-workflow.md'),ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
