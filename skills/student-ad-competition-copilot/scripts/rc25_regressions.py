"""SIMULATED regression of audited issues; native admission, no model/image calls."""
import copy,json
from review_contract import load,bound_file,digest


def run(root,manifest,save,text,stages,cli,skill):
    import validate_print_ad_run as v
    import review_workflow as workflow
    import workflow_runtime as runtime
    import series_workflow as series
    from review_projection import project,validate as projection
    from visual_review_contract import validate_layout_and_brands
    from core_return_contract import review_state,validate_return
    def case(label,fn,expected=True):
        try:result=fn();accepted=True;error=None
        except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:result=None;accepted=False;error=str(exc)
        stages.append(dict(stage='rc25-'+label,expected_accept=expected,actual_accept=accepted,error=error))
        assert accepted==expected,(label,error)
        return result
    row=copy.deepcopy(review_state(root,manifest)['assessments'][0])
    rec=load(bound_file(root,row['independent_check']));raw=load(bound_file(root,rec['raw_return']))
    lock=v.load_claim_lock(root,manifest['direction_adoption'])
    request=v.comparison_request(row,rec['blind_read'],lock)
    assert 'element_ids=[]' in request and 'brand_asset_review=[]' in request
    stages.append(dict(stage='rc25-BUG-01-empty-brand-contract',passed=True))
    more=copy.deepcopy(raw);more['brand_asset_review']=[dict(element_id='extra',looks_pasted=False,observation='SIMULATED redundant product ID')]
    case('BUG-01-extra-brand-still-rejected',lambda:validate_layout_and_brands(more,more['answers'],[]),False)
    case('BUG-01-empty-brand-accepted',lambda:validate_layout_and_brands(raw,raw['answers'],[]))
    p=row['product_triptychs'][0]
    clean=case('BUG-02-project-author-metadata',lambda:project(root,p['triptych'],p['element_id'],'rc25/projection.json'))
    value=load(bound_file(root,clean));assert 'text_checks' not in json.dumps(value) and value['source_sha256']==p['triptych']['sha256']
    bad=copy.deepcopy(value);bad['text_checks']=[dict(status='pass')]
    badref=save('rc25/leaky-projection.json',bad)
    case('BUG-02-leaky-projection-rejected',lambda:projection(root,badref),False)
    # Native chain with actual host-export interface, all identities explicitly simulated.
    row.pop('user_confirmations',None);row.pop('rework',None)
    prepared=case('DES-03-native-prepare',lambda:workflow.prepare(root,row,'SYNTHETIC-author'))
    again=workflow.prepare(root,row,'SYNTHETIC-author')
    assert prepared['state']!=again['state']
    blindraw=load(bound_file(root,load(bound_file(root,rec['blind_read']))['raw_return']))
    host=lambda label,rawref:save('rc25/'+label+'-host.json',dict(checker_context='fresh-isolated',author_session_id='SYNTHETIC-author',
        checker_session_id='SIMULATED-'+label,invocation_id='SIMULATED-'+label+'-call',started_at=runtime.now(),completed_at=runtime.now(),raw_return=rawref))
    blindhost=host('blind',save('rc25/new-blind-raw.json',blindraw))
    state=case('DES-03-blind-save-and-fixed-compare',lambda:workflow.capture_blind(root,prepared['state'],blindhost))
    secondhost=host('blind-again',save('rc25/new-blind-again-raw.json',blindraw))
    secondstate=case('BUG-02-same-pixels-new-projection-path',lambda:workflow.capture_blind(root,again['state'],secondhost))
    firstproduct=load(bound_file(root,state['state']))['row']['product_triptychs'][0]['triptych']
    secondproduct=load(bound_file(root,secondstate['state']))['row']['product_triptychs'][0]['triptych']
    assert firstproduct['sha256']==secondproduct['sha256'] and firstproduct['path']!=secondproduct['path']
    current=load(bound_file(root,state['state']));roles={x['role'] for x in state['inputs']}
    assert 'blind-read' in roles and any(x.startswith('product-triptych-metadata:') for x in roles)
    for product in current['row']['product_triptychs']:projection(root,product['triptych'],product['element_id'])
    value=copy.deepcopy(raw);value.pop('blind_read_sha256');value.pop('core_claim_sha256')
    for answer in value['answers'].values():answer.pop('blind_read_sha256')
    for product in value['comparison']['product_scene']:product.pop('role');product.pop('triptych')
    original=save('rc25/new-compare-raw.json',value)
    comparehost=host('compare',original)
    first_review=copy.deepcopy(manifest);first_review['core_creative_review']=dict(assessments=[],current_assessment_ids=[],completed_draft_render_records=[row['render_record']])
    attached=case('DES-03-native-compare-bind-admit',lambda:workflow.capture_compare(root,state['state'],comparehost,first_review))
    case('DES-03-valid-return-cannot-be-superseded',lambda:workflow.capture_compare(root,state['state'],comparehost,manifest),False)
    assert load(bound_file(root,original))==value
    attached_manifest=load(bound_file(root,attached['manifest']));newrow=attached_manifest['core_creative_review']['assessments'][-1]
    case('DES-03-native-revalidate-new-row',lambda:validate_return(root,attached_manifest,newrow))
    newrecord=load(bound_file(root,newrow['independent_check']))
    corrupted=copy.deepcopy(newrecord);corrupted['raw_return']=save('rc25/missing-original/bound-return.json',load(bound_file(root,newrecord['raw_return'])))
    corruptedrow=copy.deepcopy(newrow);corruptedrow['independent_check']=save('rc25/missing-original/compare.json',corrupted)
    case('DES-03-normalization-cannot-lose-original-lineage',lambda:validate_return(root,attached_manifest,corruptedrow),False)
    h=load(bound_file(root,blindhost));h['started_at']='2000-01-01T00:00:00+00:00'
    case('DES-03-stale-host-time-field-error',lambda:workflow.capture_blind(root,again['state'],save('rc25/stale-host.json',h)),False)
    # Batch all members first; one original message binds every exact sentence and order.
    plan=copy.deepcopy(manifest['series_plan']);plan['units']=['1','2','3']
    members=[dict(unit=u,manifest=save('rc25/member-'+u+'.json',manifest)) for u in plan['units']]
    batch=case('DES-02-all-members-checked-before-choice',lambda:series.prepare(root,members,plan))
    b=load(bound_file(root,batch));quote='SIMULATED 确认整组，知悉原检查风险。\n'+'\n'.join(m['unit']+' | '+m['statement'] for m in b['members'])
    source=save('rc25/group-source.json',dict(actor_type='human',kind='user-message',event_id='SIMULATED-group-confirm',occurred_at=runtime.now(),text=quote))
    confirmed=case('DES-02-one-message-three-locks',lambda:series.confirm(root,batch,source,quote,plan['units']))
    outputs=load(bound_file(root,confirmed))['members']
    assert len(outputs)==3 and all(load(bound_file(root,m['selection']))['source']==source for m in outputs)
    case('DES-02-order-drift-rejected',lambda:series.confirm(root,batch,source,'\n'.join(reversed(quote.splitlines())),plan['units']),False)
    changed=copy.deepcopy(manifest);changed['direction_adoption']['direction_id']='SIMULATED-stale'
    case('DES-02-member-real-change-needs-check',lambda:series.prepare(root,[dict(unit='1',manifest=save('rc25/changed-member.json',changed))],dict(plan,units=['1'])),False)
    # Mutable progress never touches the immutable plan and does not certify delivery.
    status_manifest=copy.deepcopy(manifest);status_manifest['artifacts']['run_status']='rc25/status.json';save('rc25/status.json',{})
    before=copy.deepcopy(status_manifest['series_plan'])
    case('DES-04-native-member-progress',lambda:runtime.update_status(root,status_manifest,'1',dict(status='completed',note='SIMULATED progress only')))
    assert status_manifest['series_plan']==before
    case('DES-04-substantive-plan-field-rejected',lambda:runtime.update_status(root,status_manifest,'1',dict(statement='changed')),False)
    choice=manifest['delivery_scope_selection'];originalplan=load(bound_file(root,load(bound_file(root,choice))['series_plan']))
    status_manifest['series_plan']=copy.deepcopy(originalplan);status_manifest['series_plan']['member_roles'][0]['status']='completed'
    from user_decision_contract import effective_series_plan
    case('DES-04-historical-status-not-plan-drift',lambda:effective_series_plan(root,status_manifest))
    status_manifest['series_plan']['member_roles'][0]['contribution']='SIMULATED changed meaning'
    case('DES-04-meaning-drift-still-rejected',lambda:effective_series_plan(root,status_manifest),False)
    bundle=load(bound_file(root,manifest['direction_adoption']['blind_review']));last=load(bound_file(root,bundle['rounds'][-1]))
    candidates=json.loads(bound_file(root,last['inputs'][0]['file']).read_text(encoding='utf-8'));ranking=copy.deepcopy(last['result'])
    explanation=case('DES-05-four-parallel-recommendations',lambda:series.recommendation(candidates,ranking,{c['direction_id']:'SIMULATED-user-provided' for c in candidates}))
    assert ranking==last['result'] and all(set(e)>={'communication_clarity','purpose_fit','novelty','production_risk','source'} for e in explanation)
    missing=copy.deepcopy(ranking);missing['drawability']=[]
    case('DES-05-no-invented-production-risk',lambda:series.recommendation(candidates,missing,{}),False)
    # Shared full native evidence, never an abbreviated author assertion.
    from freeze_shared_evidence import freeze
    binding=dict(binding=dict(path='02242/native-completed-binding.json',sha256=digest(root/'02242/native-completed-binding.json')),
                 request=dict(path='02242/request.json',sha256=digest(root/'02242/request.json')))
    shared=case('DES-06-shared-native-rollout',lambda:freeze(root,[binding,binding],'rc25/shared'))
    assert len(shared['objects'])==1 and len(shared['bindings'])==2
    bad=dict(binding=dict(path='02242/missing-start-time-binding.json',sha256=digest(root/'02242/missing-start-time-binding.json')),request=binding['request'])
    case('DES-06-missing-host-time-still-rejected',lambda:freeze(root,[bad],'rc25/shared-bad'),False)
    master=load(bound_file(root,binding['binding']))['evidence']
    case('DES-06-explicit-shared-master-revalidated',lambda:freeze(root,[binding,binding],'rc25/shared-master',master))
    cli('rc25-user-delivery','export_current_artwork.py',['--run-dir',root,'--manifest','manifest.json','--destination','rc25/user-delivery','--package-kind','user-delivery','--handoff','handoff/handoff.json'])
    exported=load(root/'rc25/user-delivery/CURRENT-ARTWORKS.json')
    assert not exported['audit_evidence_included'] and len(exported['files'])==1
    badmanifest=copy.deepcopy(manifest);badmanifest['delivery_scope_selection']=None
    from export_current_artwork import export
    case('DES-06-incomplete-series-not-deliverable',lambda:export(root,badmanifest,'rc25/unapproved','user-delivery',handoff='handoff/handoff.json'),False)
    start=runtime.timing(root,'SIMULATED-recovery','start');end=runtime.timing(root,'SIMULATED-recovery','end',start['token'],'failed')
    retry=runtime.timing(root,'SIMULATED-recovery','start',recovery_of=start['token']);runtime.timing(root,'SIMULATED-recovery','end',retry['token'],'passed')
    summary=runtime.timing_summary(root);assert summary['stages']['SIMULATED-recovery']['attempts']==2
    stages.append(dict(stage='rc25-DES-07-phase-failure-recovery-cost',passed=True,summary=summary))
    case('DES-07-no-unrecorded-recovery',lambda:runtime.timing(root,'SIMULATED-recovery','start',recovery_of='missing'),False)
    text('README.md','SIMULATED stale root blocker')
    case('DES-08-complete-native-current-entry',lambda:runtime.receipt(root,'manifest.json','completed',handoff='handoff/handoff.json'))
    text('README.md','SIMULATED stale blocker again')
    case('DES-08-stale-entry-rejected',lambda:runtime.check_entries(root),False)
    runtime.receipt(root,'manifest.json','completed',handoff='handoff/handoff.json')
    text('CURRENT.md',(root/'CURRENT.md').read_text(encoding='utf-8').replace('completed','blocked'))
    case('DES-08-stale-displayed-stage-rejected',lambda:runtime.check_entries(root),False)
    runtime.receipt(root,'manifest.json','completed',handoff='handoff/handoff.json')
    incomplete=copy.deepcopy(manifest);incomplete['delivery_scope_selection']=None
    save('rc25/incomplete.json',incomplete)
    case('DES-08-no-false-completion',lambda:runtime.receipt(root,'rc25/incomplete.json','completed',handoff='handoff/handoff.json'),False)
    save('rc25/regression-summary.json',dict(boundary='SIMULATED; native guards; no real approval',stages=[s for s in stages if s['stage'].startswith('rc25-')],image_generation_calls=0))
