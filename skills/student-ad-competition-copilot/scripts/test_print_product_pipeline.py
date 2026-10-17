#!/usr/bin/env python3
"""Release regression: native print-product entrypoints with SYNTHETIC pixels/records.

Run with --output-dir NEW_DIRECTORY. No network, model, image-generation or
real human approval. The local producer copies a supplied synthetic raster.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, json, os, shutil, subprocess, sys

sys.dont_write_bytecode=True
SKILL=Path(__file__).resolve().parents[1]
import validate_print_ad_run as v
from direction_purpose_contract import direction_purpose_text, validate_purpose_check
import visual_review_contract as visual
from review_contract import digest, load, fingerprint
from current_artwork_contract import validate_current

def now(): return datetime.now(timezone.utc).isoformat()


def regression_decisions(root, manifest, contract, unit, product, row, plan, q, prod, save, text, stages, cli):
    """Real entrypoints, synthetic evidence: four fixes and their fail-closed cases."""
    from user_decision_contract import effective_series_plan, assessment_confirmations
    from validate_run import validate as unified
    def check_manifest(label, m, accepted, failure=None):
        path=save('decisions/'+label+'.json',m)
        result=unified(root,root/path['path'])
        assert (not result['repair_checks']) == accepted,(label,result['repair_checks'])
        if failure:assert failure in result['repair_checks'],(label,result)
        save('decisions/'+label+'-result.json',result)
        stages.append(dict(stage=label,expected_accept=accepted,actual_accept=not result['repair_checks']))
    # Whole-image reference generation has no fictional edit masks/layer.
    assert 'edit_mask' not in plan and 'edit_mask' not in product
    visual.inspect_product_record(root,product,product['final'])
    stages.append(dict(stage='whole-image-without-edit-mask',passed=True))
    local=dict(plan,generation_method='reference-edit-label-remap',label_defect='wrong-text',
               correction_reason='SYNTHETIC actual typo',correction_bounds=[200,200,500,400])
    try:visual.validate_scene_product_plan(root,local);rejected=False
    except ValueError:rejected=True
    assert rejected,'Local edit still requires masks'
    stages.append(dict(stage='local-edit-missing-mask-rejected',expected_accept=False,actual_accept=False))

    original_pixels=load(root/'visual.json')
    doubt=dict(load(root/'product-raw.json'),label_consistent_readable=False,
               label_observation='SYNTHETIC cannot confirm the complete final stroke')
    independent=load(root/'product-independent.json')
    independent.update(raw_return=save('decisions/product-doubt-raw.json',doubt),result=doubt)
    p=dict(product,independent_confirmation=save('decisions/product-doubt-independent.json',independent))
    changed=copy.deepcopy(original_pixels);changed['units'][0]['product_integration']=[p]
    save('visual.json',changed)
    check_manifest('subjective-label-without-user-rejected',manifest,False,'final-pixel-evidence')
    source=save('decisions/human.json',dict(actor_type='human',kind='human-review',event_id='SYNTHETIC-exact-confirmation',
        occurred_at=now(),text='SYNTHETIC confirm current artwork after viewing',reviewed_artifact=unit['artifact']))
    decision=dict(kind='exact-artwork-confirmation',decision='confirm',question='label_consistent_readable',
        independent_raw=independent['raw_return'],observation=doubt['label_observation'],reviewed_artifact=unit['artifact'],
        source=source,quote='SYNTHETIC confirm current artwork after viewing',decided_at=load(root/source['path'])['occurred_at'])
    p['user_confirmations']=[save('decisions/product-confirmed.json',decision)]
    save('visual.json',changed)
    check_manifest('subjective-label-user-confirmed',manifest,True)
    assert load(root/independent['raw_return']['path'])==doubt
    # Hard errors, even with an otherwise valid user decision, stay blocked.
    for label,observation in [('wrong-brand','SYNTHETIC brand misspelled as ANOTHER'),
                              ('missing-text','SYNTHETIC missing mandatory word'),
                              ('mirrored','SYNTHETIC mirrored label'),
                              ('uncertain-but-wrong','SYNTHETIC uncertain quality; brand misspelled as ANOTHER'),
                              ('uncertain-but-omitted','SYNTHETIC uncertain final stroke; mandatory word omitted'),
                              ('uncertain-but-omitted-glyph','SYNTHETIC 字形存疑，功能文字缺“所致”')]:
        hard=dict(doubt,label_observation=observation)
        independent.update(raw_return=save('decisions/'+label+'-raw.json',hard),result=hard)
        p['independent_confirmation']=save('decisions/'+label+'-independent.json',independent)
        d=dict(decision,independent_raw=independent['raw_return'],observation=observation)
        p['user_confirmations']=[save('decisions/'+label+'-decision.json',d)]
        save('visual.json',changed)
        check_manifest(label+'-user-cannot-override',manifest,False,'final-pixel-evidence')
    independent=load(root/'decisions/product-doubt-independent.json')
    p['independent_confirmation']=save('decisions/product-doubt-independent.json',independent)
    stale=copy.deepcopy(decision);stale['reviewed_artifact']['sha256']='0'*64
    p['user_confirmations']=[save('decisions/stale-decision.json',stale)];save('visual.json',changed)
    check_manifest('stale-confirmation-rejected',manifest,False,'final-pixel-evidence')
    save('visual.json',original_pixels)

    # The same routing applies to a false independent core readability answer.
    record=load(root/row['independent_check']['path']);raw=load(root/record['raw_return']['path'])
    core=copy.deepcopy(raw);core['answers']['product_label_consistent_readable'].update(answer=False,observation=doubt['label_observation'])
    core['comparison']['product_label']['observation']=doubt['label_observation']
    core['review_issues'].append(dict(severity='hard',question='product_label_consistent_readable',reason_code='label',observation=doubt['label_observation'],priority=1))
    rec=dict(record,raw_return=save('decisions/core-doubt-raw.json',core))
    r=dict(row,answers=core['answers'],independent_check=save('decisions/core-doubt-record.json',rec))
    m=copy.deepcopy(manifest);m['core_creative_review']['assessments']=[r]
    check_manifest('core-subjective-without-user-rejected',m,False,'core-creative-pixel-review')
    d=dict(decision,question='product_label_consistent_readable',independent_raw=rec['raw_return'])
    r['user_confirmations']=[save('decisions/core-confirmed.json',d)]
    check_manifest('core-subjective-user-confirmed',m,True)
    for flag in ['compliance_check','meaning_check']:
        hard=copy.deepcopy(raw);hard[flag]['violated' if flag=='compliance_check' else 'reversed']=True
        hard[flag]['pixel_observation']='SYNTHETIC verified prohibited claim or reversed relation'
        if flag=='meaning_check':hard['answers']['claimed_relation_depicted']['answer']=False
        question='compliance' if flag=='compliance_check' else 'claimed_relation_depicted'
        code='compliance' if flag=='compliance_check' else 'main-relation-reversed'
        hard['review_issues'].append(dict(severity='hard',question=question,reason_code=code,observation=hard[flag]['pixel_observation'],priority=1))
        rec=dict(record,raw_return=save('decisions/'+flag+'-raw.json',hard))
        r=dict(row,answers=hard['answers'],independent_check=save('decisions/'+flag+'-record.json',rec))
        assert v.assessment_hard_failure(root,r)
        invalid=dict(decision,question=question,independent_raw=rec['raw_return'])
        r['user_confirmations']=[save('decisions/'+flag+'-invalid-confirmation.json',invalid)]
        try:assessment_confirmations(root,r);rejected=False
        except ValueError:rejected=True
        assert rejected
        stages.append(dict(stage=flag+'-user-cannot-override',expected_accept=False,actual_accept=False))

    # Dispatch the actual local producer at exhausted budget; preserve the
    # stopped failure handoff and generate no model call or budget increment.
    from PIL import Image, ImageDraw
    failed_image=Image.open(root/'art.png').convert('RGB')
    ImageDraw.Draw(failed_image).rectangle((240,240,280,255),fill='black')
    failed_image.save(root/'decisions/failed-label.png')
    failed_ref=dict(path='decisions/failed-label.png',sha256=digest(root/'decisions/failed-label.png'))
    allowed=Image.new('L',failed_image.size,0);ImageDraw.Draw(allowed).rectangle((200,200,499,399),fill=255)
    allowed.save(root/'decisions/local-mask.png')
    maskref=dict(path='decisions/local-mask.png',sha256=digest(root/'decisions/local-mask.png'))
    repairplan=dict(local,edit_mask=maskref,container_contact_mask=maskref)
    planref=save('decisions/local-plan.json',repairplan)
    repair=copy.deepcopy(prod);repair['image_budget'].update(limit=2,used=2)
    repair['product_scene_plans']=[repairplan]
    failed_art=dict(failed_ref,version='SYNTHETIC-failed-label',units=['1'])
    repair['main_visuals'][0].update(artifact=failed_art,core_check='failed',role='representative')
    reason='SYNTHETIC label needs local repair'
    repair['exhausted_failure_handoff']=dict(state='stopped',decision_request='additional-budget-or-change-direction',
        reason=reason,failed_artifacts=[failed_art],user_facing_copy=text('decisions/exhausted.md',reason+'\n'+failed_art['path']+'\n追加额度 / 换方向'))
    # Cumulative count must reflect this exhausted fixture, not the base record.
    repairref=save('decisions/repair-production.json',repair)
    m=copy.deepcopy(manifest);m['artifacts']['production_manifest']=repairref['path'];m['run_scope']='production-candidate'
    m.pop('core_creative_review',None)
    message=visual.image_budget_message(root,m)
    repair['exhausted_failure_handoff']['user_facing_copy']=text('decisions/exhausted.md',reason+'\n'+failed_art['path']+'\n追加额度 / 换方向\n'+message)
    repairref=save('decisions/repair-production.json',repair)
    command=text('decisions/repair.py',"from PIL import Image\na=Image.open('decisions/failed-label.png').convert('RGB')\na.paste(Image.open('official.png').convert('RGB'),(200,200))\na.save('decisions/repaired.png')\n")
    request=dict(q,id='SYNTHETIC-exhausted-local',prepared_at=now(),main_visual_action='local-composite',
        product_operation='edit',product_plan_record=repairref,input_files=[command,failed_ref,maskref,plan['official']],
        output_files=['decisions/repaired.png'],command=[sys.executable,'-B','decisions/repair.py'])
    # A distinct request and authorization keep all original history immutable.
    requestref=save('decisions/repair-request.json',request)
    auth=save('decisions/repair-auth.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-repair-auth',occurred_at=now(),text='SYNTHETIC authorize deterministic repair'))
    decision2=dict(contract['decisions'][0],id='SYNTHETIC-exhausted-auth',production_request_sha256=requestref['sha256'],source=auth,
        quote='SYNTHETIC authorize deterministic repair',checked_at=load(root/auth['path'])['occurred_at'])
    c=dict(contract,content_status='pending',production_requests=[requestref],production_receipts=[],decisions=[decision2],final_artifacts=[])
    save('decisions/repair-contract.json',c);m['review_contract']='decisions/repair-contract.json'
    save('decisions/repair-manifest.json',m)
    cli('exhausted-local-guard','guard_production.py',['--run-dir',root,'--manifest','decisions/repair-manifest.json','--request-id',request['id'],'--output','decisions/repair-guard.json','--execute'])
    receipt=load(root/'decisions/repair-guard.json');assert receipt['executed'] and receipt['production_state']=='completed'
    assert load(root/repairref['path'])['image_budget']==repair['image_budget']
    assert digest(root/'decisions/repaired.png')==digest(root/'art.png')
    stages.append(dict(stage='exhausted-deterministic-guard-executed',passed=True,image_generation_calls=0))
    repaired_ref=dict(path='decisions/repaired.png',sha256=digest(root/'decisions/repaired.png'))
    repaired_art=dict(repaired_ref,version='SYNTHETIC-repaired-label',units=['1'])
    c['production_receipts']=[dict(path='decisions/repair-guard.json',sha256=digest(root/'decisions/repair-guard.json'))]
    save('decisions/repair-contract.json',c)
    from execution_contract import verify_artwork_release
    verify_artwork_release(root,m,repaired_art)
    trip=copy.deepcopy(load(root/product['triptych']['path']))
    trip['panels']['generated']['source']=failed_ref;trip['panels']['final']['source']=repaired_ref
    visual.product_triptych(root,trip).save(root/'decisions/repair-triptych.png')
    trip['image']=dict(path='decisions/repair-triptych.png',sha256=digest(root/'decisions/repair-triptych.png'))
    tripref=save('decisions/repair-triptych.json',trip)
    independent=load(root/'product-independent.json')
    independent.update(invocation_id='SYNTHETIC-repaired-product-call',started_at=now(),completed_at=now(),
                       final=repaired_ref,triptych=tripref)
    independent['raw_return']=save('decisions/repair-independent-raw.json',independent['result'])
    repaired_image=Image.open(root/'decisions/repaired.png').convert('RGB')
    repaired_image.convert('RGBA').save(root/'decisions/repair-layer.png')
    proof=dict(before=failed_ref,after=repaired_ref,allowed_mask=maskref,**visual.exact_pixel_diff(failed_image,repaired_image,allowed))
    assert proof['changed_pixels']>0 and proof['outside_changed_pixels']==0
    corrected=dict(product,method='reference-edit-label-remap',choice_reason=repairplan['choice_reason'],
        preproduction_plan=planref,before=failed_ref,generated=failed_ref,final=repaired_ref,triptych=tripref,
        label_defect=repairplan['label_defect'],correction_reason=repairplan['correction_reason'],correction_bounds=repairplan['correction_bounds'],
        geometry=dict(rotation_degrees=0,flip_horizontal=False,flip_vertical=False,perspective_matrix=[1,0,0,0,1,0,0,0,1],
                      official_reading_vector=[1,0],label_sample_points=[[0,0]],mapping_record=text('decisions/identity-map.txt','SYNTHETIC identity mapping')),
        glyphs_changed=False,colors_changed=False,pixel_proof=proof,edit_mask=maskref,container_contact_mask=maskref,opening_mask=maskref,
        replacement_layer=dict(path='decisions/repair-layer.png',sha256=digest(root/'decisions/repair-layer.png')),
        edit_execution=c['production_receipts'][0],boundary_on_natural_edge=True,
        independent_confirmation=save('decisions/repair-independent.json',independent))
    save('decisions/repaired-product.json',corrected)
    result=visual.inspect_product_record(root,corrected,repaired_ref)
    assert result['pixel_difference']['outside_changed_pixels']==0
    stages.append(dict(stage='exhausted-repair-independent-pixel-review',passed=True,pixel_proof=proof,image_generation_calls=0))
    for label,changes in [('exhausted-model',dict(operation='external',command=None)),
                           ('exhausted-model-with-local-action',dict(operation='imagegen',main_visual_action='local-composite',command=None)),
                           ('exhausted-create',dict(operation='local',main_visual_action='create'))]:
        bad=dict(request,**changes)
        try:v.validate_main_visual_dispatch_v6(root,m,bad);rejected=False
        except ValueError as exc:rejected='Exhausted' in str(exc)
        assert rejected,label
        badref=save('decisions/'+label+'-request.json',bad)
        badcontract=dict(c,production_requests=[badref],decisions=[dict(decision2,production_request_sha256=badref['sha256'])])
        save('decisions/'+label+'-contract.json',badcontract)
        badmanifest=dict(m,review_contract='decisions/'+label+'-contract.json')
        save('decisions/'+label+'-manifest.json',badmanifest)
        result=cli(label+'-actual-guard','guard_production.py',['--run-dir',root,'--manifest','decisions/'+label+'-manifest.json','--request-id',bad['id'],'--output','decisions/'+label+'-guard.json','--execute'],accepted_codes=(1,))
        assert 'Exhausted' in result.stdout+result.stderr
        stages.append(dict(stage=label+'-blocked',expected_accept=False,actual_accept=False))
    # Leave a genuine synthetic uncertainty + confirmation in the final fixture
    # so export/handoff/unified delivery exercise this path end to end.
    p['user_confirmations']=[save('decisions/product-confirmed.json',decision)]
    save('visual.json',changed)

def regression_carryover(root, manifest, dr, bundle_ref, save, text, stages):
    """Two version upgrades use the original choice, never a carried choice."""
    original = load(root/manifest['direction_adoption']['selection_record']['path'])
    original_ref = save('migration/original-selection.json', original)
    original_sentences = dr['inputs'][0]['file']
    sentences = json.loads((root/original_sentences['path']).read_text(encoding='utf-8'))
    event = save('migration/original-event.json', dict(actor_type='human',kind='user-message',
        event_id='SYNTHETIC-original-choice',occurred_at=original['decided_at'],
        text=original['statement'],source_authorization=original['source']))
    old_version = save('migration/original-version.json', dict(skill_version='0.0.0',version='0.0.0',fixture='SYNTHETIC'))
    frozen = root/'migration/SYNTHETIC-intermediate-skill'
    shutil.copytree(SKILL, frozen)
    intermediate_version = load(frozen/'version.json')
    intermediate_version.update(skill_version='0.0.1',version='0.0.1')
    (frozen/'version.json').write_text(json.dumps(intermediate_version,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    helper = text('migration/check.py', '''from pathlib import Path
import json, sys
sys.path.insert(0, sys.argv[1])
import validate_print_ad_run as v
from direction_purpose_contract import direction_purpose_text, validate_purpose_check
root=Path(sys.argv[2])
result=v.validate_direction_blind_review(root,json.loads((root/sys.argv[3]).read_text(encoding='utf-8')))
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if result['passed'] else 1)
''')
    def migrate(label, package):
        newdr = copy.deepcopy(dr)
        newdr.update(checker_session_id='SYNTHETIC-'+label,invocation_id='SYNTHETIC-'+label+'-call',
                     input_prepared_at=now(),started_at=now(),completed_at=now())
        # Each upgrade retains its own independent return and binding.
        newdr['raw_return'] = save('migration/'+label+'-raw.json',newdr['result'])
        bundle = load(root/bundle_ref['path'])
        bundle.update(rounds=[save('migration/'+label+'-review.json',newdr)],recorded_at=now())
        newbundle = save('migration/'+label+'-bundle.json',bundle)
        choice = load(root/manifest['direction_adoption']['choice_list']['path'])
        choice['presented_at'] = now()
        newchoice = save('migration/'+label+'-choice-list.json',choice)
        version = load(package/'version.json')
        carried = dict(original,kind='user-choice-carryover',carryover=dict(
            reason='SYNTHETIC version-only migration from original actual choice',re_review_reason='skill-version-migration',
            original_selection=original_ref,original_source_event=event,original_sentences=original_sentences,
            old_version='0.0.0',old_version_manifest=old_version,new_version=version['skill_version'],
            new_version_manifest=save('migration/'+label+'-version.json',version),new_blind_review=newbundle,
            new_judgment=v.direction_judgment_v7(newdr['result'],original['direction_id'],newdr['raw_return']),carried_at=now()))
        selected = save('migration/'+label+'-carryover.json',carried)
        adopted = now()
        lock = load(root/manifest['direction_adoption']['claim_lock']['path'])
        lock.update(adopted_at=adopted,blind_review=newbundle)
        m = copy.deepcopy(manifest)
        m['direction_adoption'].update(adopted_at=adopted,blind_review=newbundle,choice_list=newchoice,
            selection_record=selected,claim_lock=save('migration/'+label+'-lock.json',lock))
        return m, carried, newdr, newbundle
    def expect(label,m,accepted,reason=None,package=SKILL):
        if package == SKILL:
            result=v.validate_direction_blind_review(root,m)
        else:
            manifest_ref=save('migration/'+label+'-manifest.json',m)
            cmd=[sys.executable,'-X','utf8','-B',str(root/helper['path']),str(package/'scripts'),str(root),manifest_ref['path']]
            r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8')
            text('logs/'+label+'.log',r.stdout+r.stderr)
            assert r.returncode in (0,1),(label,r.stderr)
            result=json.loads(r.stdout)
        assert result['passed']==accepted,(label,result)
        assert reason is None or reason in str(result['evidence']),(label,result,reason)
        stages.append(dict(stage=label,expected_accept=accepted,result=result))
    first,first_choice,_,_=migrate('upgrade-1',frozen)
    expect('carryover-first-upgrade',first,True,package=frozen)
    protected=[original_ref,original['source'],original_sentences,event,first['direction_adoption']['selection_record']]
    before={r['path']:digest(root/r['path']) for r in protected}
    latest,carried,newdr,newbundle=migrate('upgrade-2',SKILL)
    expect('carryover-second-upgrade-direct-original',latest,True)
    stale=copy.deepcopy(latest);stale['direction_adoption']['selection_record']=first['direction_adoption']['selection_record']
    expect('carryover-stale-successor-recovery',stale,False,'Create a new carryover from the earliest')
    def reject(label,mutate,reason):
        bad=copy.deepcopy(carried);mutate(bad)
        m=copy.deepcopy(latest);m['direction_adoption']['selection_record']=save('migration/'+label+'.json',bad)
        expect(label,m,False,reason)
    reject('carryover-chain-rejected',lambda s:s['carryover'].update(original_selection=first['direction_adoption']['selection_record']),'earliest kind=user-choice')
    forged=copy.deepcopy(first_choice)
    forged['carryover']['original_selection']['sha256']='0'*64
    forged_ref=save('migration/forged-chain.json',forged)
    reject('carryover-forged-chain-rejected',lambda s:s['carryover'].update(original_selection=forged_ref),'earliest kind=user-choice')
    reject('carryover-original-hash-rejected',lambda s:s['carryover']['original_selection'].update(sha256='0'*64),'changed evidence')
    altered=copy.deepcopy(sentences);altered[0]['statement']+=' '
    changed_ref=save('migration/changed-original-sentence.json',altered)
    reject('carryover-changed-sentence-rejected',lambda s:s['carryover'].update(original_sentences=changed_ref),'byte-identical')
    altered=copy.deepcopy(sentences);altered[0]['statement']='改'+altered[0]['statement'][1:]
    changed_ref=save('migration/changed-original-character.json',altered)
    reject('carryover-changed-character-rejected',lambda s:s['carryover'].update(original_sentences=changed_ref),'byte-identical')
    reject('carryover-changed-user-quote-rejected',lambda s:s.update(statement=s['statement']+' forged'),'actual source')
    false_event=load(root/event['path']);false_event['actor_type']='assistant'
    false_event_ref=save('migration/forged-source-event.json',false_event)
    reject('carryover-forged-human-event-rejected',lambda s:s['carryover'].update(original_source_event=false_event_ref),'human')
    assert before=={r['path']:digest(root/r['path']) for r in protected}
    stages.append(dict(stage='carryover-original-and-intermediate-bytes-preserved',passed=True,sha256=before))
    return latest,newdr,newbundle

def regression_a4(root, manifest, production, row, seed, direction_record, bundle_ref, inputs, feedback, references, save, text, image, stages):
    """Exercise the actual A4 dispatch interlock with synthetic independent returns."""
    from PIL import Image
    from product_relationship_contract import creative_hints
    original = copy.deepcopy(manifest['direction_adoption'])
    original_lock = load(root/original['claim_lock']['path'])
    question = 'product_action_understood_in_three_seconds'
    failures = []
    for index in (1, 2):
        im = Image.open(root/'art.png').copy();im.putpixel((index, 0), (index, 0, 0))
        observed = image('a4-failed-'+str(index)+'.png', im)
        failed = copy.deepcopy(row)
        failed.update(id='SYNTHETIC-A4-'+str(index), observed_image=observed, artifact=dict(observed,version='SYNTHETIC-failed-'+str(index),units=['1']))
        raw = copy.deepcopy(seed['comparison_raw'])
        raw['answers'][question].update(answer=False,observation='SYNTHETIC repeated unclear relation '+str(index))
        raw['review_issues']=[dict(severity='hint',question=question,reason_code='main-relation-ambiguous',observation=raw['answers'][question]['observation'],priority=1)]
        raw['core_claim_sha256']=original_lock['statement_sha256']
        failed['answers']=raw['answers']
        failed.update(review_issues=raw['review_issues'],meaning_check=raw['meaning_check'],compliance_check=raw['compliance_check'])
        check=dict(checker_context='fresh-isolated',checker_session_id='SYNTHETIC-A4-independent-'+str(index),author_session_id='SYNTHETIC-author',raw_return=save('a4-raw-'+str(index)+'.json',raw))
        failed['independent_check']=save('a4-check-'+str(index)+'.json',check)
        failed['checked_at']=now()
        failed['creative_failure_reasons']=[dict(question=i['question'],reason_code=i['reason_code'],observation=i['observation']) for i in creative_hints(raw,raw['answers'])]
        failures.append(failed)
    trigger=v.repeated_creative_failures(failures)[0]
    base=copy.deepcopy(manifest)
    base['core_creative_review']['assessments']=failures
    base['artifacts']['production_manifest']='a4-production.json'
    base['execution_control']='a4-control.json'
    prod=copy.deepcopy(production)
    save('a4-production.json',prod)
    handback='换方向 / 改动作后继续 / 照原样继续\n'+visual.image_budget_message(root,base)+'\n'+'\n'.join(x['path'] for x in trigger['failed_artifacts'])+'\n'+'\n'.join(o for r in trigger['common_reasons'] for o in r['observations'])
    handoff=dict(state='stopped',reason='SYNTHETIC repeated hint',decision_request='change-direction-or-action-or-continue',trigger_sha256=fingerprint(trigger),failed_artifacts=trigger['failed_artifacts'],common_reasons=trigger['common_reasons'],user_facing_copy=text('a4-handback.md',handback))
    prod['exhausted_failure_handoff']=handoff;save('a4-production.json',prod);save('a4-control.json',dict(state='stopped'))
    def expect(label,m,p,accepted,reason=None):
        save('a4-production.json',p)
        try:
            result=v.validate_repeated_failure_handoff(root,m,for_dispatch=True);error=None
        except (ValueError,KeyError) as exc:result=None;error=str(exc)
        assert (error is None)==accepted,(label,error)
        assert reason is None or reason in error,(label,error,reason)
        stages.append(dict(stage=label,expected_accept=accepted,actual_accept=error is None,error=error))
    expect('a4-unresolved-stop',base,prod,False,'Await')
    def user(choice):
        quote='SYNTHETIC 我选择'+choice+'；明确登记动作范围，不代表作品批准'
        source=save('a4-user-'+choice+'.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-A4-'+choice,occurred_at=now(),text=quote))
        return dict(choice=choice,source=source,quote=quote)
    same=copy.deepcopy(prod);same['exhausted_failure_handoff']['resolution']=user('照原样继续')
    expect('a4-continue-unchanged',base,same,True)
    action=copy.deepcopy(prod);resolution=user('改动作后继续');action['exhausted_failure_handoff']['resolution']=resolution
    plan=dict(recorded_at=now(),source=resolution['source'],quote=resolution['quote'],changed_scope='SYNTHETIC make the hand contact and visible relation clearer within the original sentence',baseline=trigger['failed_artifacts'][-1],original_direction_adoption=original,original_statement=text('a4-original-claim.txt',original_lock['statement']),image_budget=copy.deepcopy(prod['image_budget']))
    action['action_revision_plan']=save('a4-action-plan.json',plan)
    expect('a4-change-action-retain-lock',base,action,True)
    assert action['image_budget']==prod['image_budget']
    for label,edit,reason in [
        ('a4-expand-budget',lambda b:b.update(limit=b['limit']+1),'existing budget limit'),
        ('a4-reset-budget-revision',lambda b:b.update(revision_id='SYNTHETIC-reset'),'original bound budget snapshot'),
        ('a4-truncate-budget-history',lambda b:b.update(revision_index=2,prior_revisions=[]),'Retain every earlier')]:
        bad=copy.deepcopy(action);edit(bad['image_budget']);expect(label,base,bad,False,reason)
    for label,change,reason in [
        ('a4-unbound-user',lambda p:p.update(source=text('a4-fake-source.txt','SYNTHETIC author action')),'same actual user'),
        ('a4-empty-action',lambda p:p.update(changed_scope=''),'concrete action'),
        ('a4-change-statement-old-lock',lambda p:p.update(revised_statement='SYNTHETIC changed sentence'),'changed statement cannot reuse'),
        ('a4-forged-original',lambda p:p.update(original_statement=text('a4-forged-claim.txt','SYNTHETIC forged original')),'exact original statement')]:
        bad=copy.deepcopy(plan);change(bad);p=copy.deepcopy(action);p['action_revision_plan']=save(label+'.json',bad);expect(label,base,p,False,reason)
    # A real second direction round is needed when the locked sentence changes.
    def readopt(label,retain):
        ids={s['direction_id']: (s['direction_id'] if retain and i==0 else label+'-'+str(i)) for i,s in enumerate(seed['sentences'])}
        def remap(value):
            if isinstance(value,list):return [remap(x) for x in value]
            if isinstance(value,dict):return {k:(ids.get(x,x) if k.endswith('direction_id') else remap(x)) for k,x in value.items()}
            return value
        sentences=remap(copy.deepcopy(seed['sentences']))
        sentences[0]['statement']=sentences[0]['statement'].replace('穿过织物环','穿过展开的织物环')
        content=json.dumps(sentences,ensure_ascii=False,indent=2)+'\n'
        raw=remap(load(root/direction_record['raw_return']['path']))
        dr=copy.deepcopy(direction_record)
        dr.update(checker_session_id='SYNTHETIC-'+label,invocation_id='SYNTHETIC-'+label+'-call',input_prepared_at=now(),started_at=now(),completed_at=now(),inputs=[dict(role='direction-sentences',file=text(label+'-sentences.json',content)),*inputs[1:]],request=text(label+'-request.txt',getattr(v,'direction_request_v12' if manifest['direction_contract']=='print-direction-v12' else 'direction_request_v11' if manifest['direction_contract']=='print-direction-v11' else 'direction_request_v10')(content,references,feedback,*([(root/inputs[3]['file']['path']).read_text(encoding='utf-8')] if manifest['direction_contract']=='print-direction-v12' else []))),raw_return=save(label+'-raw.json',raw),result=raw)
        bundle=load(root/bundle_ref['path']);bundle['rounds'].append(save(label+'-record.json',dr));bundle['recorded_at']=now()
        origins=remap(copy.deepcopy(seed['origins']))
        bundle['origins'] += [x for x in origins if not retain or x['direction_id']!=original['direction_id']]
        newbundle=save(label+'-bundle.json',bundle)
        rows=v.direction_choice_rows_v7(sentences,raw)
        visible='\n'.join('## '+x['direction_id']+'\n'+x['statement']+'\n'+x['basis']+'\n'+v.direction_choice_judgment_text_v6(x)+'\n'+x['checker_comment']+'\n'+v.direction_choice_causal_text_v8(x['causal_check'])+('\n'+direction_purpose_text(next(p for p in raw['purpose_check'] if p['direction_id']==x['direction_id'])) if 'purpose_check' in raw else '') for x in rows)
        choice=save(label+'-choice.json',dict(presented_at=now(),rows=rows,causal_advisories=v.direction_choice_advisory_rows_v7(sentences,raw),product_meaning_advisories=raw['product_meaning_hints'],**({'purpose_advisories':raw['purpose_check']} if 'purpose_check' in raw else {}),user_facing_copy=text(label+'-choice.md',visible)))
        ident=sentences[0]['direction_id'];statement='SYNTHETIC select '+ident
        selection=save(label+'-selection.json',dict(kind='user-choice',actor='user',direction_id=ident,decided_at=now(),statement=statement,source=text(label+'-selection.txt',statement)))
        adopted=now();lock=save(label+'-lock.json',dict(direction_id=ident,statement=sentences[0]['statement'],statement_sha256=v.claim_digest(sentences[0]['statement']),adopted_at=adopted,blind_review=newbundle))
        adoption=dict(original,direction_id=ident,adopted_at=adopted,blind_review=newbundle,selection_record=selection,claim_lock=lock,choice_list=choice,previous_adoptions=[original])
        return dict(base,selected_direction=ident,direction_adoption=adoption),sentences[0]['statement']
    amended,newclaim=readopt('SYNTHETIC-action-amended',True)
    result=v.validate_direction_blind_review(root,amended);assert result['passed'],result
    newplan=dict(plan,revised_statement=newclaim);p=copy.deepcopy(action);p['action_revision_plan']=save('a4-amended-plan.json',newplan)
    expect('a4-change-action-new-claim-new-round',amended,p,True)
    # Historical and current locks can share the direction ID, but an old current
    # draft cannot satisfy the amended statement. Consume the actual earlier core
    # record to exercise lock routing rather than only checking the A4 decision.
    old_current=copy.deepcopy(amended)
    old_current['core_creative_review']=copy.deepcopy(manifest['core_creative_review'])
    old_current['artifacts']['production_manifest']=manifest['artifacts']['production_manifest']
    result=next(r for r in v.validate_creative_contract(root,old_current) if r['name']=='core-creative-pixel-review')
    assert not result['passed'] and 'Current draft must use current adopted direction lock' in str(result['evidence']),result
    stages.append(dict(stage='a4-amended-current-old-claim-rejected',expected_accept=False,result=result))
    bad=copy.deepcopy(amended);bad['direction_adoption']['claim_lock']=original['claim_lock']
    expect('a4-amended-reuses-old-lock',bad,p,False,'Claim lock must bind')
    bad=copy.deepcopy(amended);bad['direction_adoption'].pop('previous_adoptions')
    expect('a4-amended-hides-history',bad,p,False,'new lock and independent')
    swap=copy.deepcopy(prod);swap['exhausted_failure_handoff']['resolution']=user('换方向')
    changed,_=readopt('SYNTHETIC-direction-new',False)
    swap['image_budget']=dict(swap['image_budget'],direction_id=changed['selected_direction'])
    expect('a4-change-direction',changed,swap,True)
    expect('a4-change-direction-same-id',base,prod | {'exhausted_failure_handoff':swap['exhausted_failure_handoff']},False,'different adopted direction')
    forged=copy.deepcopy(same);forged['exhausted_failure_handoff']['resolution']['quote']='SYNTHETIC 照原样继续 fabricated'
    expect('a4-fabricated-user-quote',base,forged,False,'quotation')
    save(manifest['artifacts']['production_manifest'],production)


def run_pipeline(root):
    from PIL import Image, ImageDraw
    root=root.resolve();root.mkdir(parents=True,exist_ok=False)
    seed=load(SKILL/'references/validation/print-product-pipeline-fixture.json')
    gates=load(SKILL/'references/tracks/print-ad/quality-gates.json')
    current=gates['definition_set_id']=='print-ad.0.22.0'
    dc='print-direction-v12' if current else 'print-direction-v10'
    cc='print-core-product-v8' if current else 'print-core-product-v7'
    stages=[]
    def ref(name):return dict(path=name,sha256=digest(root/name))
    def save(name,value):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return ref(name)
    def text(name,value):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8');return ref(name)
    def image(name,im):im.save(root/name);return ref(name)
    def cli(label,script,args,accepted_codes=(0,)):
        cmd=[sys.executable,'-X','utf8','-B',str(SKILL/'scripts'/script),*map(str,args)]
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
        r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8')
        text('logs/'+label+'.log',r.stdout+r.stderr)
        stages.append(dict(stage=label,command=cmd,exit_code=r.returncode))
        assert r.returncode in accepted_codes,(label,r.stdout+r.stderr)
        return r
    def require_result(label,result):
        stages.append(dict(stage=label,result=result));assert result['passed'],result
    def meta(rubric,label):
        return dict(rubric_version=rubric,checker_context='fresh-isolated',author_session_id='SYNTHETIC-author',checker_session_id='SYNTHETIC-'+label,invocation_id='SYNTHETIC-'+label+'-call',unavailable_metadata={})

    cli('method-query','query_case_library.py',['--kind','method','--competition','academy-award','--category','print-ad','--problem','产品','--output',root/'methods.json'])
    cli('case-query','query_case_library.py',['--kind','case','--competition','academy-award','--category','print-ad','--limit','100','--output',root/'cases.json'])
    methods=load(root/'methods.json')
    assert {r['record']['method_id'] for r in methods['results']}=={d['method_id'] for d in seed['decisions']}
    constraint=text('constraint.txt','SYNTHETIC official hard constraint; no real authority')
    for decision in seed['decisions']:
        if decision.get('rejection_basis')=='official-hard-constraint':decision['rejection_evidence']=constraint
    retrieval=save('retrieval.json',dict(run_id='SYNTHETIC-pipeline',recorded_at=now(),original_problem='产品',attempts=[dict(output=ref('methods.json'),fallback_terms=[],returned_method_ids=[r['record']['method_id'] for r in methods['results']])],decisions=seed['decisions']))
    cases=save('case-references.json',dict(query_output=ref('cases.json'),cases=[],empty_reason='SYNTHETIC: active pack has no target-applicable Academy print references; complete actual query retained.'))
    sentences=seed['sentences'];ident=sentences[0]['direction_id'];claim=sentences[0]['statement']
    content=json.dumps(sentences,ensure_ascii=False,indent=2)+'\n'
    references=json.dumps(dict(cases=[],empty_reason=load(root/'case-references.json')['empty_reason']),ensure_ascii=False,indent=2)+'\n'
    feedback=(SKILL/'references/feedback/direction-counterexamples.json').read_text(encoding='utf-8')
    inputs=[dict(role=role,file=text(name,val)) for role,name,val in [('direction-sentences','sentences.json',content),('reference-mechanisms','references.json',references),('feedback-counterexamples','feedback.json',feedback)]]
    purpose_source=text('purpose-source.txt','SYNTHETIC official purpose: support normal activity and remember product care.\n')
    purpose_content=json.dumps(dict(source=purpose_source,excerpts=[dict(line_start=1,line_end=1,quote='SYNTHETIC official purpose: support normal activity and remember product care.')]),ensure_ascii=False,indent=2)+'\n'
    if current:inputs.append(dict(role='proposition-purpose',file=text('purpose.json',purpose_content)))
    raw=copy.deepcopy(seed['direction_result'])
    if current:
        raw['purpose_check']=[dict(direction_id=x['direction_id'],audience_takeaway='SYNTHETIC audience shifts to avoiding activity' if i==0 else 'SYNTHETIC product care',judgment='drift' if i==0 else 'aligned',purpose_quote='support normal activity',observation='SYNTHETIC independent purpose observation',opposite_relation=None) for i,x in enumerate(sentences)]
        validate_purpose_check(raw,sentences,purpose_content)
        baseline=copy.deepcopy(raw);baseline['purpose_check'][0]['judgment']='aligned'
        assert v.direction_choice_rows_v6(sentences,raw)==v.direction_choice_rows_v6(sentences,baseline)
        stages.append(dict(stage='purpose-drift-hint-preserves-ranking-and-adoption',passed=True))
        note=text('product-role-group-selfcheck.md','SYNTHETIC author self-check: '+', '.join(x['direction_id']+'=display-object' for x in sentences)+'\nAll display: brief requirement or convenience? SYNTHETIC justified common packaging comparison; no role quota or gate.\n')
        assert len(raw['ranking'])==len(sentences) and all(x['drawable'] for x in raw['drawability'])
        stages.append(dict(stage='product-role-group-hint-no-quota-or-guard',passed=True,note=note))
    raw['causal_check']=[dict(direction_id=x['direction_id'],effect_source='人的动作',reason='SYNTHETIC autonomous action',attributed_to_product=False,product_participates=False,reminder=False) for x in sentences]
    raw['product_meaning_hints']=[dict(direction_id=x['direction_id'],audience_meaning='SYNTHETIC visible product meaning',weak=False,observation='SYNTHETIC fixture judgment') for x in sentences]
    for item in raw['reference_assessment']:item.update(reaches_reference=None,reason='SYNTHETIC no applicable references in active pack')
    dr=meta(dc,'direction');dr.update(input_prepared_at=now(),started_at=now(),completed_at=now(),inputs=inputs,case_references=cases,request=text('direction-request.txt',getattr(v,'direction_request_v12' if current else 'direction_request_v10')(content,references,feedback,*([purpose_content] if current else []))),raw_return=save('direction-raw.json',raw),result=raw)
    bundle=save('direction-bundle.json',dict(run_id='SYNTHETIC-pipeline',recorded_at=now(),rounds=[save('direction-record.json',dr)],origins=seed['origins'],superseded_rounds=[]))
    rows=v.direction_choice_rows_v7(sentences,raw);advice=v.direction_choice_advisory_rows_v7(sentences,raw)
    visible='\n'.join('## '+x['direction_id']+'\n'+x['statement']+'\n'+x['basis']+'\n'+v.direction_choice_judgment_text_v6(x)+'\n'+x['checker_comment']+'\n'+v.direction_choice_causal_text_v8(x['causal_check'])+('\n'+direction_purpose_text(next(p for p in raw['purpose_check'] if p['direction_id']==x['direction_id'])) if 'purpose_check' in raw else '') for x in rows)
    choice=save('choice.json',dict(presented_at=now(),rows=rows,causal_advisories=advice,product_meaning_advisories=raw['product_meaning_hints'],**({'purpose_advisories':raw['purpose_check']} if 'purpose_check' in raw else {}),user_facing_copy=text('choice.md',visible)))
    selected=save('selection.json',dict(kind='user-choice',actor='user',direction_id=ident,decided_at=now(),statement='SYNTHETIC select '+ident,source=text('user-choice.txt','SYNTHETIC select '+ident)))
    adopted=now();lock=save('claim-lock.json',dict(direction_id=ident,statement=claim,statement_sha256=v.claim_digest(claim),adopted_at=adopted,blind_review=bundle))
    manifest=dict(schema_version='0.4.0',run_id='SYNTHETIC-pipeline',competition='academy-award',category='print-ad',brief_id='SYNTHETIC-brief',selected_direction=ident,series_mode='single',run_scope='production-candidate',aigc_used='no',method_validation_status='not-claimed',creative_contract='print-core-v4',direction_contract=dc,product_contract='print-product-v3',core_review_contract=cc,secondary_copy_contract='print-secondary-copy-v2',direction_provenance_contract='print-direction-provenance-v1',execution_profile='bound-production-v1',execution_control='control.json',review_contract='review.json',artifacts={'quality_gate_results':'gates.json','production_manifest':'production-before.json'})
    manifest['direction_adoption']=dict(direction_id=ident,adopted_at=adopted,method_retrieval=retrieval,blind_review=bundle,selection_mode='user',selection_record=selected,claim_lock=lock,choice_list=choice)
    require_result('direction-choice-and-lock',v.validate_direction_blind_review(root,manifest))
    manifest,dr,bundle=regression_carryover(root,manifest,dr,bundle,save,text,stages)
    # Query migration is tested without altering historical times/paths.
    original=load(root/'cases.json');historical=copy.deepcopy(original)
    historical['execution']['pack']=str(root/'removed-skill/references/case-library/v0.2.1')
    historical['execution']['command'][1]=str(root/'removed-skill/scripts/query_case_library.py')
    for label,mutate,accepted in [('moved-identical-pack',lambda q:None,True),('different-pack',lambda q:q['execution'].update(pack_manifest_sha256='0'*64),False),('different-state',lambda q:q['eligibility'].update(state_fingerprint='0'*64),False),('different-input',lambda q:q['eligibility'].update(input_fingerprint='0'*64),False),('expanded-query',lambda q:q['query'].update(terms=['extra']),False),('expanded-results',lambda q:q['results'].append(copy.deepcopy(q['results'][0])),False),('altered-card',lambda q:q['results'][0]['record'].update(title='SYNTHETIC altered'),False)]:
        q=copy.deepcopy(historical);mutate(q)
        rr=save('negative-'+label+'.json',dict(query_output=save('query-'+label+'.json',q),cases=[],empty_reason=load(root/'case-references.json')['empty_reason']))
        try:v.direction_case_projection(root,rr,datetime.now(timezone.utc),'academy-award',qualified_scope=True);passed=True
        except ValueError:passed=False
        assert passed==accepted,(label,passed)
        stages.append(dict(stage=label,expected_accept=accepted,actual_accept=passed))

    # Supplied synthetic raster and masks. The producer copies it after release.
    native=Image.new('RGB',(1260,945),'white');draw=ImageDraw.Draw(native)
    draw.rectangle((200,200,499,399),fill='green');draw.text((20,20),'SYNTHETIC TITLE',fill='black');draw.text((240,240),'BRAND CATEGORY MARK',fill='white')
    supplied=image('supplied.png',native);official=image('official.png',native.crop((200,200,500,400)))
    baseline=image('before.png',Image.new('RGB',native.size,'white'))
    mask=Image.new('L',native.size,255);maskref=image('mask.png',mask)
    plan=dict(contract='print-product-plan-v4',element_id='cell',registered_at=now(),official=official,role='scene-object',generation_method='reference-generate-label',choice_reason='SYNTHETIC direct label generation contract simulation',container_contact_structure='SYNTHETIC housing and contact',canvas_size=list(native.size),missing_structure_assets=[],posture_and_perspective=dict(action_and_support='SYNTHETIC supported in housing with visible contact',camera_relation='SYNTHETIC oblique view of housing and product face',perspective_and_occlusion='SYNTHETIC far end foreshortened, contact edges occlude the product'))
    planref=save('product-plan.json',plan)
    prod=dict(main_visual_contract='main-visual-v1',main_visuals=[],image_budget=dict(direction_id=ident,revision_id='SYNTHETIC',revision_index=1,prior_revisions=[],limit=2,used=0),product_scene_plans=[plan],mandatory_brand_asset_placements=[])
    prodref=save('production-before.json',prod)
    manifest.update(required_brand_assets=[],brand_asset_requirements_source=text('brief.txt','SYNTHETIC no mandatory extra brand assets'),series_plan=dict(mode='single',units=['1'],reason='SYNTHETIC one artwork',user_requested_series=False,member_roles=[dict(unit='1',benefit_or_action=claim,contribution='SYNTHETIC one complete relation')],shared_art_direction='SYNTHETIC geometric raster',scope_basis=[ref('brief.txt')]))
    save('control.json',dict(run_id=manifest['run_id'],state='active',monitoring='not-requested'))
    save('gates.json',dict(definition_set_id=gates['definition_set_id']))
    # The same historical identity rule also applies to method retrieval.
    original_methods=load(root/'methods.json');moved_methods=copy.deepcopy(original_methods)
    moved_methods['execution']['pack']=str(root/'removed-skill/references/case-library/v0.2.1')
    moved_methods['execution']['command'][1]=str(root/'removed-skill/scripts/query_case_library.py')
    for label,mutate,accepted in [('moved-method-pack',lambda r:None,True),('changed-method-pack',lambda r:r['execution'].update(pack_manifest_sha256='0'*64),False),('changed-method-fingerprint',lambda r:r['eligibility'].update(state_fingerprint='0'*64),False),('altered-method-card',lambda r:r['results'][0]['record'].update(name='SYNTHETIC forged card'),False)]:
        mr=copy.deepcopy(moved_methods);mutate(mr);save('methods.json',mr)
        retrieval_data=load(root/'retrieval.json');retrieval_data['attempts'][0]['output']=ref('methods.json');save('retrieval.json',retrieval_data);manifest['direction_adoption']['method_retrieval']=ref('retrieval.json')
        result=next(x for x in v.validate_creative_contract(root,dict(manifest,run_scope='concept-only')) if x['name']=='method-retrieval-before-adoption')
        assert result['passed']==accepted,(label,result)
        stages.append(dict(stage=label,expected_accept=accepted,actual_accept=result['passed']))
    save('methods.json',original_methods);retrieval_data['attempts'][0]['output']=ref('methods.json');save('retrieval.json',retrieval_data);manifest['direction_adoption']['method_retrieval']=ref('retrieval.json')
    producer=text('producer.py',"from pathlib import Path\nPath('art.png').write_bytes(Path('supplied.png').read_bytes())\nprint('SYNTHETIC local raster copy; zero image-generation calls')\n")
    # Pre-production direction material is intentionally a different exact object.
    representative=dict(ref('choice.md'),version='SYNTHETIC-choices',units=[ident])
    q=dict(id='SYNTHETIC-produce',prepared_at=now(),operation='local',execution_profile='bound-production-v1',main_visual_action='create',main_visual_source='user-asset',product_operation='generate',product_targets=[dict(element_id='cell',role='scene-object')],product_plan_record=prodref,input_files=[producer,supplied,official,maskref],brand_asset_mode='not-used',brand_asset_reason='SYNTHETIC supplied raster; official product input separately bound',output_files=['art.png'],output_scope=['1'],representatives=[representative],command=[sys.executable,'-B','producer.py'])
    qref=save('request.json',q);auth=save('authorization.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-auth',occurred_at=now(),text='SYNTHETIC authorize fixture request'))
    decision=dict(id='SYNTHETIC-auth',checked_at=load(root/'authorization.json')['occurred_at'],source=auth,quote='SYNTHETIC authorize fixture request',stage='production-authorization',decision='pass',reviewed_artifacts=[representative],production_request_sha256=qref['sha256'])
    contract=dict(schema_version='1.0.0',run_id=manifest['run_id'],track='print-ad',content_status='pending',decisions=[decision],production_requests=[qref],production_receipts=[],final_artifacts=[])
    save('review.json',contract);save('manifest.json',manifest)
    # Test the actual production guard, before any producer runs.
    from jsonschema import Draft202012Validator
    schema=load(SKILL/'references/schemas/print-ad-run-manifest.schema.json')
    validator=Draft202012Validator({'$ref':'#/$defs/main_visual_production_product_v6_whole_image','$defs':schema['$defs']})
    validator.validate(prod)
    for label,mutate in [
        ('product-plan-missing-pose',lambda p:p.pop('posture_and_perspective')),
        ('product-plan-missing-camera',lambda p:p['posture_and_perspective'].pop('camera_relation')),
        ('product-plan-blank-perspective',lambda p:p['posture_and_perspective'].update(perspective_and_occlusion='   '))]:
        bad=copy.deepcopy(prod);mutate(bad['product_scene_plans'][0])
        assert list(validator.iter_errors(bad)),label
        badref=save('negative-'+label+'-production.json',bad)
        badmanifest=copy.deepcopy(manifest);badmanifest['artifacts']['production_manifest']=badref['path']
        badq=copy.deepcopy(q);badq['product_plan_record']=badref
        badqref=save('negative-'+label+'-request.json',badq)
        badcontract=copy.deepcopy(contract);badcontract['production_requests']=[badqref]
        badcontract['decisions'][0]['production_request_sha256']=badqref['sha256']
        save('review.json',badcontract);save('negative-'+label+'-manifest.json',badmanifest)
        r=cli(label,'guard_production.py',['--run-dir',root,'--manifest','negative-'+label+'-manifest.json','--request-id',q['id'],'--output',label+'-guard.json','--execute'],accepted_codes=(1,))
        assert 'posture_and_perspective' in r.stdout+r.stderr,(label,r.stdout+r.stderr)
        assert not (root/'art.png').exists(),label
    save('review.json',contract)
    cli('production-guard-and-local-copy','guard_production.py',['--run-dir',root,'--manifest','manifest.json','--request-id',q['id'],'--output','guard.json','--execute'])
    receipt=load(root/'guard.json');assert receipt['executed'] and receipt['production_state']=='completed'
    contract['production_receipts']=[ref('guard.json')];save('review.json',contract)
    art=dict(ref('art.png'),version='SYNTHETIC-v1',units=['1'])
    cli('render-and-current-views','prepare_visual_views.py',['--run-dir',root,'--source','art.png','--native','art.png','--version',art['version'],'--unit','1','--renderer','SYNTHETIC raster reopen','--execution-evidence','guard.json','--output-dir','views','--thumbnail-width','420','--full-page-detail','--target-renderer-verified','--manifest','manifest.json','--complete-artwork'])
    render=load(root/'views/render-record.json');thumb=next(x['file'] for x in render['views'] if x['scale']=='thumbnail');renderref=ref('views/render-record.json')
    final=ref('art.png');layer=native.convert('RGBA');layerref=image('layer.png',layer)
    trip=dict(panels={k:dict(source=s,bounds=b,zoom=2) for k,s,b in [('official',official,[0,0,300,200]),('generated',final,[200,200,500,400]),('final',final,[200,200,500,400])]},text_checks=[dict(kind=k,official_text=t,final_text=t,status='pass',generated_observation='SYNTHETIC label pixels',observation='SYNTHETIC identical words') for k,t in [('brand','BRAND'),('category','CATEGORY'),('mark','MARK')]])
    trip['image']=image('triptych.png',visual.product_triptych(root,trip));tripref=save('triptych.json',trip)
    confirmation=dict(label_consistent_readable=True,label_observation='SYNTHETIC identical readable label',residue_absent=True,residue_observation='SYNTHETIC no old product',scene_integration=True,scene_observation='SYNTHETIC contact geometry')
    independent=dict(checker_context='fresh-isolated',author_session_id='SYNTHETIC-author',checker_session_id='SYNTHETIC-product',invocation_id='SYNTHETIC-product-call',started_at=now(),completed_at=now(),official=official,final=final,triptych=tripref,raw_return=save('product-raw.json',confirmation),result=confirmation)
    product=dict(contract='print-product-v3',element_id='cell',role='scene-object',method='reference-generate-label',choice_reason=plan['choice_reason'],preproduction_plan=planref,official=official,before=baseline,final=final,generated=final,generation_reference=official,edit_execution=ref('guard.json'),occlusion_observation='SYNTHETIC no occlusion',triptych=tripref,independent_confirmation=save('product-independent.json',independent),pixel_proof=dict(before=baseline,after=final,allowed_mask=maskref,**visual.exact_pixel_diff(Image.open(root/'before.png'),native,mask)))
    tripbinding=dict(element_id='cell',role='scene-object',triptych=tripref)
    row=dict(id='SYNTHETIC-core',artifact=art,render_record=renderref,observed_image=final,official_product_asset=official,core_action=claim,core_claim_sha256=v.claim_digest(claim),direction_id=ident,assessment_method='independent-review',product_contract='print-product-v3',core_review_contract=cc,product_triptychs=[tripbinding],required_brand_assets=[],proposition_message=ref('brief.txt'))
    blind=meta('print-core-blind-v6' if current else 'print-core-blind-v5','blind')
    blind.update(input_prepared_at=now(),started_at=now(),completed_at=now(),saved_at=now(),inputs=[dict(role='artwork',file=final)],request=text('blind-request.txt',getattr(v,'INDEPENDENT_BLIND_RUBRIC_V6' if current else 'INDEPENDENT_BLIND_RUBRIC_V5')),raw_return=save('blind-raw.json',seed['blind_raw']))
    blind['input_manifest_sha256']=v.blind_input_digest(blind['inputs']);blindref=save('blind.json',blind)
    rawcore=copy.deepcopy(seed['comparison_raw']);rawcore['blind_read_sha256']=blindref['sha256'];rawcore['core_claim_sha256']=row['core_claim_sha256']
    for answer in rawcore['answers'].values():answer['blind_read_sha256']=blindref['sha256']
    rawcore['comparison']['product_scene']=[dict(tripbinding,answer=True,observation=rawcore['answers']['product_in_scene']['observation'])]
    row['answers']=rawcore['answers']
    compare=meta(cc,'compare');compare.update(started_at=now(),completed_at=now(),blind_read=blindref,core_claim_sha256=row['core_claim_sha256'],inputs=[dict(role=k,file=f) for k,f in [('artwork',final),('official-product-asset',official),('core-action',text('claim.txt',claim)),('thumbnail',thumb),('proposition-message',ref('brief.txt')),('product-triptych:cell',trip['image'])]],request=text('compare-request.txt',getattr(v,'INDEPENDENT_COMPARE_RUBRIC_PRODUCT_V8' if current else 'INDEPENDENT_COMPARE_RUBRIC_PRODUCT_V7')+'\n核心动作/关系：'+claim+'\n盲读记录SHA256：'+blindref['sha256']+'\n锁定声明SHA256：'+row['core_claim_sha256']),raw_return=save('compare-raw.json',rawcore))
    row['independent_check']=save('compare.json',compare);row['checked_at']=now()
    v.validate_blind_core(root,row,render,compare,set(),load(root/'claim-lock.json'));stages.append(dict(stage='blind-compare-eight-questions-product-scene-layout',passed=True,question_count=len(row['answers'])))
    # The new orientation observation uses the existing advisory boundary.
    from product_relationship_contract import hard_failure
    orientation=copy.deepcopy(rawcore)
    concern='SYNTHETIC product view resembles official asset; grip/view may be mismatched, no verified pixel conflict'
    orientation['answers']['product_in_scene']['observation']=concern
    orientation['scene_evidence']=dict(basis='indirect-concern',observation=concern)
    orientation['review_issues'].append(dict(severity='hint',question='brand-asset',reason_code='brand-asset-pasted',observation=concern,priority=1))
    assert not hard_failure(orientation,orientation['answers'])
    stages.append(dict(stage='product-orientation-concern-only-hints',passed=True,question_7=True))
    orientation['review_issues'][-1]['severity']='hard'
    try:hard_failure(orientation,orientation['answers']);rejected=False
    except ValueError:rejected=True
    assert rejected
    stages.append(dict(stage='product-orientation-subjective-hard-rejected',passed=True))
    conflict=copy.deepcopy(rawcore)
    conflict['answers']['product_in_scene'].update(answer=False,observation='SYNTHETIC actual intersecting contact pixels')
    conflict['scene_evidence']=dict(basis='visible-conflict',observation=conflict['answers']['product_in_scene']['observation'])
    conflict['review_issues'].append(dict(severity='hard',question='product_in_scene',reason_code='scene-integration',observation=conflict['scene_evidence']['observation'],priority=1))
    assert hard_failure(conflict,conflict['answers'])
    stages.append(dict(stage='product-visible-conflict-still-hard',passed=True))
    unit=dict(artifact=art,render_record=renderref,checks=[dict(check=k,status='pass',views=['native'],observation='SYNTHETIC pixel observation',assessment_method='author-inspection') for k in visual.BASE_CHECKS|{'visual-only-meaning','communication-clarity','visible-element-delete-test'}],critical_review=[dict(kind=k,status='pass' if k=='brand-product' else 'not-applicable',views=['native'],detail_required=False,observation='SYNTHETIC inspection',evidence=[official] if k=='brand-product' else []) for k in ['key-text','brand-product','data-citations']],issues=[],product_present=True,product_presence_observation='SYNTHETIC one visible product',product_integration=[product],text_elements=[dict(element_id='title',role='headline',text='SYNTHETIC TITLE',bounds=[20,20,170,40]),dict(element_id='mark',role='brand-product-mark',text='BRAND CATEGORY MARK',bounds=[240,240,400,270])],secondary_copy=dict(contract='print-secondary-copy-v2',used=False,reason='SYNTHETIC picture and title are sufficient; no secondary copy',element_ids=[],title_element_ids=['title'],checks={k:'not-applicable' for k in ['hierarchy','thumbnail_legibility','series_consistency','copy_semantics']}))
    manifest['artifacts']['visual_review']='visual.json';save('visual.json',dict(schema_version='2.7.0',run_id=manifest['run_id'],run_scope='production-candidate',units=[unit]))
    prod['main_visuals']=[dict(artifact=art,source='user-asset',role='passed',core_check='passed',sources=[supplied],evidence=[ref('guard.json')])]
    save('production-after.json',prod);manifest['artifacts']['production_manifest']='production-after.json'
    manifest['proposition_message']=row['proposition_message']
    manifest['core_creative_review']=dict(assessments=[row],current_assessment_ids=[row['id']],completed_draft_render_records=[renderref])
    for result in visual.validate_visual_review(root,manifest):require_result('production-visual-evidence-2.7.0',result)
    # Series first-member production review, before any final approval/delivery.
    for key in ['brief_evidence','direction_cards','concept_gate','official_asset_manifest','human_visual_review']:
        manifest['artifacts'][key]=key+'.json';save(key+'.json',dict(boundary='SYNTHETIC fixture evidence',evidence=[]))
    save('gates.json',dict(document_type='gate-results',schema_version='0.1.0',definition_set_id=gates['definition_set_id'],track='print-ad',run_id=manifest['run_id'],results=[dict(gate_id=g['gate_id'],status='pass',passed_check_ids=[c['check_id'] for c in g['checks']],failed_check_ids=[],boundaries=[],waiver_reason=None,checked_at=now(),reviewers=[dict(type='human',id='SYNTHETIC-reviewer'),dict(type='machine',id='SYNTHETIC-checker')],evidence_paths=['compare.json']) for g in gates['gates']]))
    supplyreview=save('external-production-review.json',dict(status='pass',scope='production-candidate',assets=[supplied],observation='SYNTHETIC supplied bitmap decoded'))
    manifest['visual_generation_capability']=dict(status='unavailable',provider=None,operations=[],checked_at=now(),evidence='SYNTHETIC supplied pixels',user_decision='use-external-assets',impact_acknowledged=True,external_supply=dict(kind='provided-assets',status='ready',scope='production-candidate',evidence='SYNTHETIC supplied fixture bitmap',assets=[supplied],review=supplyreview))
    production_manifest=copy.deepcopy(manifest)
    production_manifest.update(series_mode='series',visual_review_request_ids=[q['id']])
    production_manifest['series_plan']=dict(manifest['series_plan'],mode='series',units=['1','2','3'],shared_mechanism='SYNTHETIC shared product relation',member_roles=[dict(unit=str(i),benefit_or_action=claim,contribution='SYNTHETIC member '+str(i)) for i in range(1,4)])
    contract['final_artifacts']=[art];save('review.json',contract)
    production_manifest['artifacts']['technical_validation']='production-technical.json'
    production_manifest['artifacts']['run_status']='production-status.json'
    save('production-status.json',dict(content_review_status='pending',review_decision_ids=[],method_run_complete=False))
    save('production-technical.json',dict(technical_validation_status='pass',failure_names=[],files=[dict(path=str(root/'art.png'),sha256=art['sha256'])],boundary='SYNTHETIC raster record'))
    save('production-manifest.json',production_manifest)
    cli('series-first-production-unified','validate_run.py',['--run-dir',root,'--manifest','production-manifest.json','--output','production-unified.json'])
    first=load(root/'production-unified.json')
    assert first['technical_pass'] and not first['content_pass'] and not first['delivery_complete'] and first['status']=='passed',first
    assert not first['repair_checks'] and any(x['name']=='final-pixel-evidence' and x['passed'] for x in first['run_validation']['checks']),first
    stages.append(dict(stage='series-first-production-candidate',passed=True,series_units=['1','2','3'],current_units=['1'],content_pass=False,delivery_complete=False))
    def reject_visual(label,m,expected):
        result=visual.validate_visual_review(root,m)
        assert any(not x['passed'] and expected in str(x['evidence']) for x in result),(label,result)
        stages.append(dict(stage=label,expected_accept=False,result=result))
    original_contract=copy.deepcopy(contract)
    for label,mutate,reason in [
        ('production-unknown-request',lambda m:m.update(visual_review_request_ids=['unknown']),'unknown or cancelled'),
        ('production-unselected-owner',lambda m:m.update(visual_review_request_ids=[]),'unique current'),
        ('production-duplicate-current',lambda m:m['core_creative_review'].update(current_assessment_ids=[row['id'],row['id']]),'unique current'),
        ('production-duplicate-assessment-record',lambda m:m['core_creative_review']['assessments'].append(copy.deepcopy(m['core_creative_review']['assessments'][0])),'exactly one complete artwork'),
        ('production-forged-output',lambda m:m['core_creative_review']['assessments'][0]['artifact'].update(sha256='0'*64),'changed evidence'),
        ('production-same-unit-old-object',lambda m:m['core_creative_review']['assessments'][0].update(artifact=dict(supplied,version=art['version'],units=['1'])),'guard release')]:
        m=copy.deepcopy(production_manifest);mutate(m);reject_visual(label,m,reason)
    broken=copy.deepcopy(receipt);broken['production_state']='running';contract['production_receipts']=[save('uncompleted-guard.json',broken)];save('review.json',contract)
    reject_visual('production-uncompleted-release',production_manifest,'guard release')
    contract=copy.deepcopy(original_contract);save('review.json',contract)
    other=copy.deepcopy(q);other['id']='SYNTHETIC-unselected'
    otherref=save('other-request.json',other)
    contract['production_requests'].append(otherref);save('review.json',contract)
    reject_visual('production-known-unselected-owner',dict(production_manifest,visual_review_request_ids=[other['id']]),'selected non-cancelled')
    cancellation=save('other-cancelled.json',dict(request_id=other['id'],request_sha256=otherref['sha256'],executed=False,reason='SYNTHETIC unstarted request cancelled',cancelled_at=now()))
    contract['production_cancellations']=[cancellation];save('review.json',contract)
    reject_visual('production-selected-cancelled-request',dict(production_manifest,visual_review_request_ids=[other['id']]),'unknown or cancelled')
    contract=copy.deepcopy(original_contract);save('review.json',contract)
    for label,edit,reason in [
        ('production-duplicate-pixel-unit',lambda p:p['units'].append(copy.deepcopy(p['units'][0])),'Duplicate reviewed visual unit'),
        ('production-stale-artifact-version',lambda p:p['units'][0]['artifact'].update(version='SYNTHETIC-old'),'Current render source differs')]:
        pixels=load(root/'visual.json');edit(pixels);save('visual.json',pixels)
        result=visual.validate_visual_review(root,production_manifest)
        assert any(not x['passed'] for x in result),(label,result)
        stages.append(dict(stage=label,expected_accept=False,result=result))
        save('visual.json',dict(schema_version='2.7.0',run_id=manifest['run_id'],run_scope='production-candidate',units=[unit]))
    # A request authorized for two units must not be represented by one current page.
    multi=copy.deepcopy(q);multi.update(id='SYNTHETIC-two-units',output_scope=['1','2'])
    multiref=save('two-unit-request.json',multi);multi_receipt=copy.deepcopy(receipt)
    multi_receipt.update(request_id=multi['id'],request_sha256=multiref['sha256'],request=multi)
    contract['production_requests']=[multiref];contract['production_receipts']=[save('two-unit-guard.json',multi_receipt)];save('review.json',contract)
    reject_visual('production-output-scope-sample',dict(production_manifest,visual_review_request_ids=[multi['id']]),'every selected request output_scope')
    contract=copy.deepcopy(original_contract);save('review.json',contract)
    regression_a4(root,manifest,prod,row,seed,dr,bundle,inputs,feedback,references,save,text,image,stages)
    manifest['run_scope']='delivery-candidate';contract['final_artifacts']=[art];save('review.json',contract)
    save('visual.json',dict(schema_version='2.7.0',run_id=manifest['run_id'],run_scope='delivery-candidate',units=[unit]))
    for result in visual.validate_visual_review(root,manifest):require_result('delivery-visual-evidence-2.7.0',result)
    bundle_current=dict(native=final,preview=thumb,purpose='creative-master',render_record=save('current-render.json',dict(source=final,execution_evidence=ref('guard.json'),render=final,compared_artifact=art,correspondence='matched',observation='SYNTHETIC raster bytes identical')),process_review=dict(render=final,status='clear',observation='SYNTHETIC no process labels'),no_scene_reason='SYNTHETIC raster is native source',native_inspection=dict(observation='SYNTHETIC raster reopened',evidence=ref('guard.json')))
    member=dict(art,current_source=bundle_current)
    contract['final_artifacts']=[member]
    finalsource=save('final-human.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-final',occurred_at=now(),text='SYNTHETIC approve fixture final'))
    finaldecision=dict(id='SYNTHETIC-final',checked_at=load(root/'final-human.json')['occurred_at'],stage='final',decision='pass',source=finalsource,quote='SYNTHETIC approve fixture final',reviewed_artifacts=[art])
    contract['decisions'].append(finaldecision);contract['content_status']='pass';save('review.json',contract)
    manifest['run_scope']='delivery-candidate';save('visual.json',dict(schema_version='2.7.0',run_id=manifest['run_id'],run_scope='delivery-candidate',units=[unit]))
    for key in ['brief_evidence','direction_cards','concept_gate','official_asset_manifest','human_visual_review']:manifest['artifacts'][key]=key+'.json';save(key+'.json',dict(boundary='SYNTHETIC fixture evidence',evidence=[]))
    manifest['artifacts'].update(run_status='status.json',technical_validation='technical.json',delivery_manifest='delivery.json')
    save('status.json',dict(content_review_status='pass',review_decision_ids=[finaldecision['id']],method_run_complete=True))
    save('technical.json',dict(technical_validation_status='pass',failure_names=[],files=[dict(path=str(root/'art.png'),sha256=art['sha256'])],boundary='SYNTHETIC technical result tests record consumption; not a print specification certification.'))
    save('delivery.json',dict(delivered_at=now(),final_artifacts=[member]))
    save('gates.json',dict(document_type='gate-results',schema_version='0.1.0',definition_set_id=gates['definition_set_id'],track='print-ad',run_id=manifest['run_id'],results=[dict(gate_id=g['gate_id'],status='pass',passed_check_ids=[c['check_id'] for c in g['checks']],failed_check_ids=[],boundaries=[],waiver_reason=None,checked_at=now(),reviewers=[dict(type='human',id='SYNTHETIC-reviewer'),dict(type='machine',id='SYNTHETIC-checker')],evidence_paths=['compare.json']) for g in gates['gates']]))
    supplyreview=save('external-review.json',dict(status='pass',scope='delivery-candidate',assets=[supplied],observation='SYNTHETIC supplied bitmap decoded'))
    manifest['visual_generation_capability']=dict(status='unavailable',provider=None,operations=[],checked_at=now(),evidence='SYNTHETIC local supplied pixels; no generation invoked',user_decision='use-external-assets',impact_acknowledged=True,external_supply=dict(kind='provided-assets',status='ready',scope='delivery-candidate',evidence='SYNTHETIC supplied fixture bitmap',assets=[supplied],review=supplyreview))
    save('manifest.json',manifest)
    regression_decisions(root,manifest,contract,unit,product,row,plan,q,prod,save,text,stages,cli)
    cli('unified-check','validate_run.py',['--run-dir',root,'--manifest','manifest.json','--output','unified.json'])
    check=load(root/'unified.json');assert check['technical_pass'] and check['content_pass'] and not check['delivery_complete'],check
    incomplete_series=dict(manifest,series_mode='series',series_plan=production_manifest['series_plan'])
    try:validate_current(root,incomplete_series,contract);rejected=False
    except ValueError as exc:rejected='Current members differ from the effective series plan' in str(exc)
    assert rejected, 'Delivery candidate must still require all three series members'
    stages.append(dict(stage='delivery-series-first-only-rejected',expected_accept=False,actual_accept=False))
    fullplan=save('decisions/full-series-plan.json',production_manifest['series_plan'])
    scope_source=save('decisions/scope-source.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-partial-series',
        occurred_at=now(),text='SYNTHETIC deliver series member 1 only'))
    selection=dict(kind='partial-series-delivery',series_plan=fullplan,units=['1'],source=scope_source,
        quote='SYNTHETIC deliver series member 1 only',decided_at=load(root/scope_source['path'])['occurred_at'])
    manifest.update(series_mode='series',series_plan=production_manifest['series_plan'],delivery_scope_selection=save('decisions/scope-selection.json',selection))
    validate_current(root,manifest,contract)
    assert v.validate(root,root/save('decisions/partial-series-manifest.json',manifest)['path'])['status']=='passed'
    stages.append(dict(stage='explicit-partial-series-delivery',passed=True,planned_units=['1','2','3'],current_units=['1']))
    unauthorized=copy.deepcopy(manifest);unauthorized.pop('delivery_scope_selection')
    try:validate_current(root,unauthorized,contract);rejected=False
    except ValueError:rejected=True
    assert rejected
    stages.append(dict(stage='partial-series-without-user-rejected',expected_accept=False,actual_accept=False))
    save('manifest.json',manifest)
    validate_current(root,manifest,contract);stages.append(dict(stage='current-artwork',passed=True))
    cli('export','export_current_artwork.py',['--run-dir',root,'--manifest','manifest.json','--destination','export'])
    readiness=load(SKILL/'references/templates/submission-readiness.template.json');readiness.update(run_id=manifest['run_id'],track='print-ad',competition='academy-award',method_scope='artwork-delivery')
    readiness['rule_verification']=dict(status='verified-current',source_url='https://example.com/synthetic-rules',checked_at=now(),evidence_path='brief.txt')
    readiness['citations']=dict(status='not-applicable',open_items=[],rationale='SYNTHETIC no external research claims')
    save('readiness-input.json',readiness)
    cli('prepare-delivery','prepare_handoff.py',['--run-dir',root,'--manifest','manifest.json','--output-dir','handoff','--readiness-input','readiness-input.json'])
    cli('unified-delivery','validate_run.py',['--run-dir',root,'--manifest','manifest.json','--handoff','handoff/handoff.json','--output','delivery-check.json'])
    check=load(root/'delivery-check.json');assert check['delivery_complete'] and check['content_pass'] and check['technical_pass'] and not check['submission_ready'],check
    handoff=load(root/'handoff/handoff.json')
    assert len(handoff['user_decisions'])==2 and any(d.get('independent_answer') is False for d in handoff['user_decisions'])
    report=dict(status='passed',boundary=seed['boundary'],contracts=dict(direction=dc,core=cc,product='print-product-v3',visual='2.7.0',gates=gates['definition_set_id']),stages=stages,delivery_complete=True,image_generation_calls=0,real_approval_created=False)
    save('pipeline-result.json',report);print(json.dumps({k:report[k] for k in ['status','contracts','delivery_complete','image_generation_calls']},ensure_ascii=False));return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);args=p.parse_args();run_pipeline(args.output_dir)

if __name__=='__main__':main()
