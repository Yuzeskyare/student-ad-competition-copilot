"""SIMULATED regression fixtures; execute native validators/guards, zero models."""
import copy, json, shutil, sys, zipfile
from datetime import datetime,timezone
from pathlib import Path
from review_contract import load, digest, bound_file

def run(root, manifest, save, text, stages, cli, skill):
    import validate_print_ad_run as v
    from core_return_contract import review_state, validate_return
    from product_relationship_contract import validate_issues,hard_failure
    from execution_contract import verify_artwork_release
    from package_upgrade_contract import validate_historical_guard
    def now():return datetime.now(timezone.utc).isoformat()
    def case(label,fn,ok=True,reason=None):
        try:fn();accepted=True;error=None
        except (ValueError,KeyError,TypeError) as e:accepted=False;error=str(e)
        assert accepted==ok,(label,error)
        if reason:assert reason in error,(label,error)
        stages.append(dict(stage='rc4-'+label,expected_accept=ok,actual_accept=accepted,error=error))
    m=copy.deepcopy(manifest);m['run_scope']='production-candidate'
    active=review_state(root,m)['assessments'][0]
    row=copy.deepcopy(active);rec=load(bound_file(root,row['independent_check']));raw=load(bound_file(root,rec['raw_return']))
    lock=v.load_claim_lock(root,m['direction_adoption'])
    rec['request']=text('rc4/current-fixed-request.txt',v.comparison_request(row,rec['blind_read'],lock))
    def bind(label,value):
        record=copy.deepcopy(rec);record['raw_return']=save('rc4/'+label+'-raw.json',value)
        r=copy.deepcopy(row);r['answers']=copy.deepcopy(value['answers']);r['independent_check']=save('rc4/'+label+'-record.json',record)
        candidate=copy.deepcopy(m);candidate['core_creative_review']=dict(assessments=[r],current_assessment_ids=[r['id']],completed_draft_render_records=[r['render_record']])
        return candidate,r
    cm,cr=bind('consistent',raw)
    case('new-fixed-request-with-text-checks',lambda:validate_return(root,cm,cr))
    hint=copy.deepcopy(raw);hint['review_issues'].append(dict(severity='hint',question='local-detail',reason_code='local-detail',observation='SIMULATED overall meaning holds; transition near contact can be clearer',priority=1))
    hm,hr=bind('local-detail',hint)
    case('true-answer-local-detail-retained',lambda:validate_return(root,hm,hr))
    assert not hard_failure(hint,hint['answers'])
    contradictory=copy.deepcopy(raw);contradictory['review_issues'].append(dict(severity='hint',question='claimed_relation_depicted',reason_code='claim-unfulfilled',observation=raw['answers']['claimed_relation_depicted']['observation'],priority=1))
    bm,br=bind('contradictory',contradictory)
    case('contradictory-return-still-invalid',lambda:validate_return(root,bm,br),False,'Creative hints')
    case('unrejected-invalid-return-still-blocks',lambda:require_pass(v.validate_main_visual_provenance_v6(root,bm)),False,'Creative hints')
    png=copy.deepcopy(raw);png['comparison']['product_scene'][0]['triptych']=load(bound_file(root,row['product_triptychs'][0]['triptych']))['image']
    pm,pr=bind('png-instead-of-json',png)
    case('triptych-png-still-invalid',lambda:validate_return(root,pm,pr),False,'triptych')
    # Preserve a real blind ambiguity and assert both contradictory classifications.
    blind=load(bound_file(root,rec['blind_read']));blindraw=load(bound_file(root,blind['raw_return']))
    blindraw['ambiguities']=['SIMULATED unclear small fold']
    blind['raw_return']=save('rc4/ambiguity-blind-raw.json',blindraw)
    blindref=save('rc4/ambiguity-blind.json',blind)
    for aspect,flag,ok in [('secondary',False,True),('other-main',False,False),('action-direction',False,False)]:
        value=copy.deepcopy(raw);value['blind_read_sha256']=blindref['sha256']
        for answer in value['answers'].values():answer['blind_read_sha256']=blindref['sha256']
        value['comparison']['ambiguities']=[dict(blind_ambiguity=blindraw['ambiguities'][0],affects_main_relation=flag,aspect=aspect,observation='SIMULATED localized fold observation')]
        am,ar=bind('ambiguity-'+aspect,value)
        rr=load(bound_file(root,ar['independent_check']));rr['blind_read']=blindref
        rr['request']=text('rc4/ambiguity-'+aspect+'-request.txt',v.comparison_request(ar,blindref,lock))
        ar['independent_check']=save('rc4/ambiguity-'+aspect+'-record2.json',rr)
        case('ambiguity-'+aspect,lambda:validate_return(root,am,ar),ok,None if ok else 'Classify')
    for flag in ('mirrored','inverted','misspelled','pseudo_text'):
        value=copy.deepcopy(raw);value['comparison']['product_label']['checks'][0][flag]=True
        mm,mr=bind(flag+'-contradiction',value)
        case(flag+'-cannot-be-true',lambda:validate_return(root,mm,mr),False,'must fail question 6')
        value['answers']['product_label_consistent_readable'].update(answer=False,observation='SIMULATED verified '+flag+' product letters versus official pixels')
        value['review_issues'].append(dict(severity='hard',question='product_label_consistent_readable',reason_code='label',observation=value['answers']['product_label_consistent_readable']['observation'],priority=1))
        mm,mr=bind(flag+'-hard',value)
        case(flag+'-recorded-hard',lambda:validate_return(root,mm,mr))
        assert hard_failure(value,value['answers'])
    omitted=copy.deepcopy(raw);omitted['comparison']['product_label'].pop('checks')
    om,orr=bind('missing-text-checks',omitted)
    case('missing-independent-text-checks',lambda:validate_return(root,om,orr),False,'cover every')
    # A terminal user rejection retires this exact draft, including exhausted
    # invalid attempts; it never edits or invalidates those retained returns.
    contract=load(root/m['review_contract']);quote='SIMULATED I reject these exact pixels; revise next draft'
    src=save('rc4/reject-source.json',dict(actor_type='human',kind='user-message',event_id='SIMULATED-rc4-reject',occurred_at=now(),text=quote))
    rejection=dict(id='SIMULATED-rc4-reject',stage='final',decision='reject',source=src,quote=quote,checked_at=load(root/src['path'])['occurred_at'],reviewed_artifacts=[br['artifact']])
    rc=copy.deepcopy(contract);rc['decisions'].append(rejection);rc['content_status']='fail'
    bm['review_contract']=save('rc4/rejected-contract.json',rc)['path']
    original_hash=digest(bound_file(root,load(bound_file(root,br['independent_check']))['raw_return']))
    state=review_state(root,bm);assert not state['assessments'] and state['terminal_rejection_audit'][0]['content_pass_granted'] is False
    case('rejected-invalid-draft-can-progress',lambda:require_pass(v.validate_main_visual_provenance_v6(root,bm)))
    missing=copy.deepcopy(m);missing['core_creative_review']=dict(assessments=[],current_assessment_ids=[],completed_draft_render_records=[row['render_record']])
    case('unrejected-draft-with-no-return-blocked',lambda:require_pass(v.validate_main_visual_provenance_v6(root,missing)),False,'valid independent core return')
    missing['review_contract']=bm['review_contract']
    case('rejected-draft-with-no-return-can-progress',lambda:require_pass(v.validate_main_visual_provenance_v6(root,missing)))

    case('rejected-draft-cannot-deliver',lambda:review_state(root,dict(bm,run_scope='delivery-candidate')),False,'cannot pass or be delivered')
    badsource=copy.deepcopy(load(root/src['path']));badsource['actor_type']='model'
    badrc=copy.deepcopy(rc);badrc['decisions'][-1]['source']=save('rc4/model-source.json',badsource)
    case('model-cannot-forge-rejection',lambda:review_state(root,dict(bm,review_contract=save('rc4/model-contract.json',badrc)['path'])),False,'traceable human')
    assert digest(bound_file(root,load(bound_file(root,br['independent_check']))['raw_return']))==original_hash
    stages.append(dict(stage='rc4-rejected-raw-unchanged',passed=True))

    # Create an authentic native guard under a SIMULATED previous package.
    old=root/'rc4/SIMULATED-old-package/student-ad-competition-copilot'
    shutil.copytree(skill,old)
    text('rc4/SIMULATED-old-package/student-ad-competition-copilot/scripts/simulated_package_marker.py','"""SIMULATED historical package identity only."""\n')
    version=load(old/'version.json');version.update(version='SIMULATED-previous',skill_version='SIMULATED-previous')
    version['files']=[dict(path=p.relative_to(old).as_posix(),sha256=digest(p),bytes=p.stat().st_size) for p in sorted(old.rglob('*')) if p.is_file() and p.name!='version.json' and '__pycache__' not in p.parts]
    save('rc4/SIMULATED-old-package/student-ad-competition-copilot/version.json',version)
    def archive(label,package):
        dest=root/('rc4/'+label+'.zip')
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(package.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:z.write(p,'student-ad-competition-copilot/'+p.relative_to(package).as_posix())
        return dict(path=dest.relative_to(root).as_posix(),sha256=digest(dest))
    oldzip=archive('SIMULATED-old',old);newzip=archive('current-package',skill)
    authorization=save('rc4/history-author.json',dict(actor_type='human',kind='user-message',event_id='SIMULATED-history-author',occurred_at=now(),text='SIMULATED authorize local copy'))
    request=dict(id='SIMULATED-history-copy',prepared_at=now(),operation='local',execution_profile='bound-production-v1',brand_asset_mode='not-used',brand_asset_reason='SIMULATED provided pixels',input_files=[row['observed_image']],output_files=['rc4/history-copy.png'],output_scope=['1'],representatives=[row['artifact']],command=[sys.executable,'-c',"import shutil;shutil.copyfile('"+row['observed_image']['path']+"','rc4/history-copy.png')"])
    req=save('rc4/history-request.json',request)
    decision=dict(id='SIMULATED-history-author',stage='production-authorization',decision='pass',source=authorization,quote='SIMULATED authorize local copy',checked_at=load(root/authorization['path'])['occurred_at'],reviewed_artifacts=[row['artifact']],production_request_sha256=req['sha256'])
    hc=dict(schema_version='1.0.0',run_id='SIMULATED-rc4-history',track='ad-copy',content_status='pending',decisions=[decision],production_requests=[req],production_receipts=[],final_artifacts=[])
    hcr=save('rc4/history-contract.json',hc)
    ctl=save('rc4/history-control.json',dict(run_id=hc['run_id'],state='active',monitoring='not-requested'))
    hm=dict(schema_version='0.4.0',run_id=hc['run_id'],category='ad-copy',review_contract=hcr['path'],execution_control=ctl['path'])
    hmanifest=save('rc4/history-manifest.json',hm)
    import subprocess,os
    cmd=[sys.executable,'-X','utf8','-B',str(old/'scripts/guard_production.py'),'--run-dir',str(root),'--manifest',hmanifest['path'],'--request-id',request['id'],'--output','rc4/history-guard.json','--execute']
    result=subprocess.run(cmd,cwd=root,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,encoding='utf-8');text('rc4/history-guard-command.log',result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    stages.append(dict(stage='rc4-native-old-package-guard-executed',command=cmd,exit_code=0))
    guardref=dict(path='rc4/history-guard.json',sha256=digest(root/'rc4/history-guard.json'));hc['production_receipts']=[guardref];save(hcr['path'],hc)
    output=dict(path='rc4/history-copy.png',sha256=digest(root/'rc4/history-copy.png'))
    case('unregistered-old-release-rejected',lambda:verify_artwork_release(root,hm,output),False,'absent from registered')
    versions=load(skill/'version.json')
    chain=dict(kind='package-upgrade-chain',run_id=hc['run_id'],upgrades=[dict(from_version=version['version'],to_version=versions['version'],from_package=oldzip,to_package=newzip,upgraded_at=now())])
    hm['package_upgrades']=save('rc4/upgrade-chain.json',chain)
    case('registered-old-release-accepted',lambda:verify_artwork_release(root,hm,output))
    assert verify_artwork_release(root,hm,output)['source_package']['version']=='SIMULATED-previous'
    recheck_manifest=save('rc4/recheck-history-manifest.json',hm)
    cli('rc4-history-native-recheck','recheck_history.py',['--run-dir',root,'--manifest',recheck_manifest['path'],'--output','rc4/new-history-receipt.json'])
    native=load(root/'rc4/new-history-receipt.json')
    assert native['image_generation_calls']==0 and native['production_executed'] is False and native['content_pass_granted'] is False

    guard=load(root/guardref['path'])
    for label,mutate in [('forged-identity',lambda g:g['guard_identity']['checker_sha256'].update({'scripts/guard_production.py':'0'*64})),('wrong-run',lambda g:g.update(run_id='SIMULATED-wrong-run')),('wrong-request',lambda g:g.update(request_sha256='0'*64)),('wrong-decision',lambda g:g.update(decision_sha256='0'*64)),('wrong-output',lambda g:g['outputs'][0].update(sha256='0'*64))]:
        forged=copy.deepcopy(guard);mutate(forged)
        case(label,lambda:validate_historical_guard(root,hm,forged,request,req,{decision['id']:decision}),False)
    badchain=copy.deepcopy(chain);badchain['upgrades'][0]['from_version']='SIMULATED-unlisted'
    case('version-archive-mismatch',lambda:verify_artwork_release(root,dict(hm,package_upgrades=save('rc4/wrong-version.json',badchain)),output),False,'version/archive')
    badchain=copy.deepcopy(chain);badchain['upgrades'][0]['from_package']['sha256']='0'*64
    case('forged-installation-hash',lambda:verify_artwork_release(root,dict(hm,package_upgrades=save('rc4/wrong-package.json',badchain)),output),False,'Missing or changed evidence')
    # Persist an inspectable probe for the external rc.3/rc.4 red-green audit.
    save('rc4/red-green-probes.json',dict(local_detail_manifest=save('rc4/local-detail-manifest.json',bind_manifest(m,hr))['path'],local_detail_row=hr,mirrored_manifest=save('rc4/mirror-contradiction-manifest.json',bind_manifest(m,bind('mirror-probe',dict_with_mirror(raw))[1]))['path'],history_manifest=save('rc4/upgraded-history-manifest.json',hm)['path'],history_artifact=output))

def require_pass(value):
    if not value['passed']:raise ValueError(str(value['evidence']))
def bind_manifest(m,row):
    r=copy.deepcopy(m);r['core_creative_review']=dict(assessments=[row],current_assessment_ids=[row['id']],completed_draft_render_records=[row['render_record']]);return r
def dict_with_mirror(raw):
    r=copy.deepcopy(raw);r['comparison']['product_label']['checks'][0]['mirrored']=True;return r
