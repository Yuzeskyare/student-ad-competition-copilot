#!/usr/bin/env python3
"""Release regression: native print-product entrypoints with SYNTHETIC pixels/records.

Run with --output-dir NEW_DIRECTORY. No network, model, image-generation or
real human approval. The local producer copies a supplied synthetic raster.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, json, os, subprocess, sys

sys.dont_write_bytecode=True
SKILL=Path(__file__).resolve().parents[1]
import validate_print_ad_run as v
import visual_review_contract as visual
from review_contract import digest, load
from current_artwork_contract import validate_current

def now(): return datetime.now(timezone.utc).isoformat()

def run_pipeline(root):
    from PIL import Image, ImageDraw
    root=root.resolve();root.mkdir(parents=True,exist_ok=False)
    seed=load(SKILL/'references/validation/print-product-pipeline-fixture.json')
    gates=load(SKILL/'references/tracks/print-ad/quality-gates.json')
    current=gates['definition_set_id']=='print-ad.0.22.0'
    dc='print-direction-v11' if current else 'print-direction-v10'
    cc='print-core-product-v8' if current else 'print-core-product-v7'
    stages=[]
    def ref(name):return dict(path=name,sha256=digest(root/name))
    def save(name,value):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return ref(name)
    def text(name,value):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8');return ref(name)
    def image(name,im):im.save(root/name);return ref(name)
    def cli(label,script,args):
        cmd=[sys.executable,'-X','utf8','-B',str(SKILL/'scripts'/script),*map(str,args)]
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
        r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8')
        text('logs/'+label+'.log',r.stdout+r.stderr)
        stages.append(dict(stage=label,command=cmd,exit_code=r.returncode))
        assert r.returncode==0,(label,r.stdout+r.stderr)
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
    raw=copy.deepcopy(seed['direction_result'])
    raw['causal_check']=[dict(direction_id=x['direction_id'],effect_source='人的动作',reason='SYNTHETIC autonomous action',attributed_to_product=False,product_participates=False,reminder=False) for x in sentences]
    raw['product_meaning_hints']=[dict(direction_id=x['direction_id'],audience_meaning='SYNTHETIC visible product meaning',weak=False,observation='SYNTHETIC fixture judgment') for x in sentences]
    for item in raw['reference_assessment']:item.update(reaches_reference=None,reason='SYNTHETIC no applicable references in active pack')
    dr=meta(dc,'direction');dr.update(input_prepared_at=now(),started_at=now(),completed_at=now(),inputs=inputs,case_references=cases,request=text('direction-request.txt',getattr(v,'direction_request_v11' if current else 'direction_request_v10')(content,references,feedback)),raw_return=save('direction-raw.json',raw),result=raw)
    bundle=save('direction-bundle.json',dict(run_id='SYNTHETIC-pipeline',recorded_at=now(),rounds=[save('direction-record.json',dr)],origins=seed['origins'],superseded_rounds=[]))
    rows=v.direction_choice_rows_v7(sentences,raw);advice=v.direction_choice_advisory_rows_v7(sentences,raw)
    visible='\n'.join('## '+x['direction_id']+'\n'+x['statement']+'\n'+x['basis']+'\n'+v.direction_choice_judgment_text_v6(x)+'\n'+x['checker_comment']+'\n'+v.direction_choice_causal_text_v8(x['causal_check']) for x in rows)
    choice=save('choice.json',dict(presented_at=now(),rows=rows,causal_advisories=advice,product_meaning_advisories=raw['product_meaning_hints'],user_facing_copy=text('choice.md',visible)))
    selected=save('selection.json',dict(kind='user-choice',actor='user',direction_id=ident,decided_at=now(),statement='SYNTHETIC select '+ident,source=text('user-choice.txt','SYNTHETIC select '+ident)))
    adopted=now();lock=save('claim-lock.json',dict(direction_id=ident,statement=claim,statement_sha256=v.claim_digest(claim),adopted_at=adopted,blind_review=bundle))
    manifest=dict(schema_version='0.4.0',run_id='SYNTHETIC-pipeline',competition='academy-award',category='print-ad',brief_id='SYNTHETIC-brief',selected_direction=ident,series_mode='single',run_scope='production-candidate',aigc_used='no',method_validation_status='not-claimed',creative_contract='print-core-v4',direction_contract=dc,product_contract='print-product-v3',core_review_contract=cc,secondary_copy_contract='print-secondary-copy-v2',direction_provenance_contract='print-direction-provenance-v1',execution_profile='bound-production-v1',execution_control='control.json',review_contract='review.json',artifacts={'quality_gate_results':'gates.json','production_manifest':'production-before.json'})
    manifest['direction_adoption']=dict(direction_id=ident,adopted_at=adopted,method_retrieval=retrieval,blind_review=bundle,selection_mode='user',selection_record=selected,claim_lock=lock,choice_list=choice)
    require_result('direction-choice-and-lock',v.validate_direction_blind_review(root,manifest))
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
    plan=dict(contract='print-product-plan-v3',element_id='cell',registered_at=now(),official=official,role='scene-object',generation_method='reference-generate-label',choice_reason='SYNTHETIC direct label generation contract simulation',container_contact_structure='SYNTHETIC housing and contact',canvas_size=list(native.size),edit_mask=maskref,container_contact_mask=maskref,missing_structure_assets=[])
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
    representative=dict(supplied,version='SYNTHETIC-input',units=['1'])
    q=dict(id='SYNTHETIC-produce',prepared_at=now(),operation='local',execution_profile='bound-production-v1',main_visual_action='create',main_visual_source='user-asset',product_operation='generate',product_targets=[dict(element_id='cell',role='scene-object')],product_plan_record=prodref,input_files=[producer,supplied,official,maskref],brand_asset_mode='not-used',brand_asset_reason='SYNTHETIC supplied raster; official product input separately bound',output_files=['art.png'],output_scope=['1'],representatives=[representative],command=[sys.executable,'-B','producer.py'])
    qref=save('request.json',q);auth=save('authorization.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-auth',occurred_at=now(),text='SYNTHETIC authorize fixture request'))
    decision=dict(id='SYNTHETIC-auth',checked_at=load(root/'authorization.json')['occurred_at'],source=auth,quote='SYNTHETIC authorize fixture request',stage='production-authorization',decision='pass',reviewed_artifacts=[representative],production_request_sha256=qref['sha256'])
    contract=dict(schema_version='1.0.0',run_id=manifest['run_id'],track='print-ad',content_status='pending',decisions=[decision],production_requests=[qref],production_receipts=[],final_artifacts=[])
    save('review.json',contract);save('manifest.json',manifest)
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
    product=dict(contract='print-product-v3',element_id='cell',role='scene-object',method='reference-generate-label',choice_reason=plan['choice_reason'],preproduction_plan=planref,official=official,before=baseline,final=final,generated=final,generation_reference=official,edit_execution=ref('guard.json'),edit_mask=maskref,container_contact_mask=maskref,opening_mask=maskref,replacement_layer=layerref,boundary_on_natural_edge=True,occlusion_observation='SYNTHETIC no occlusion',triptych=tripref,independent_confirmation=save('product-independent.json',independent),pixel_proof=dict(before=baseline,after=final,allowed_mask=maskref,**visual.exact_pixel_diff(Image.open(root/'before.png'),native,mask)))
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
    unit=dict(artifact=art,render_record=renderref,checks=[dict(check=k,status='pass',views=['native'],observation='SYNTHETIC pixel observation',assessment_method='author-inspection') for k in visual.BASE_CHECKS|{'visual-only-meaning','communication-clarity','visible-element-delete-test'}],critical_review=[dict(kind=k,status='pass' if k=='brand-product' else 'not-applicable',views=['native'],detail_required=False,observation='SYNTHETIC inspection',evidence=[official] if k=='brand-product' else []) for k in ['key-text','brand-product','data-citations']],issues=[],product_present=True,product_presence_observation='SYNTHETIC one visible product',product_integration=[product],text_elements=[dict(element_id='title',role='headline',text='SYNTHETIC TITLE',bounds=[20,20,170,40]),dict(element_id='mark',role='brand-product-mark',text='BRAND CATEGORY MARK',bounds=[240,240,400,270])],secondary_copy=dict(contract='print-secondary-copy-v2',used=False,reason='SYNTHETIC picture and title are sufficient; no secondary copy',element_ids=[],title_element_ids=['title'],checks={k:'not-applicable' for k in ['hierarchy','thumbnail_legibility','series_consistency','copy_semantics']}))
    manifest['run_scope']='delivery-candidate';contract['final_artifacts']=[art];save('review.json',contract)
    manifest['artifacts']['visual_review']='visual.json';save('visual.json',dict(schema_version='2.6.0',run_id=manifest['run_id'],run_scope='delivery-candidate',units=[unit]))
    prod['main_visuals']=[dict(artifact=art,source='user-asset',role='passed',core_check='passed',sources=[supplied],evidence=[ref('guard.json')])]
    save('production-after.json',prod);manifest['artifacts']['production_manifest']='production-after.json'
    manifest['proposition_message']=row['proposition_message']
    manifest['core_creative_review']=dict(assessments=[row],current_assessment_ids=[row['id']],completed_draft_render_records=[renderref])
    for result in visual.validate_visual_review(root,manifest):require_result('visual-evidence-2.6.0',result)
    bundle_current=dict(native=final,preview=thumb,purpose='creative-master',render_record=save('current-render.json',dict(source=final,execution_evidence=ref('guard.json'),render=final,compared_artifact=art,correspondence='matched',observation='SYNTHETIC raster bytes identical')),process_review=dict(render=final,status='clear',observation='SYNTHETIC no process labels'),no_scene_reason='SYNTHETIC raster is native source',native_inspection=dict(observation='SYNTHETIC raster reopened',evidence=ref('guard.json')))
    member=dict(art,current_source=bundle_current)
    contract['final_artifacts']=[member]
    finalsource=save('final-human.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-final',occurred_at=now(),text='SYNTHETIC approve fixture final'))
    finaldecision=dict(id='SYNTHETIC-final',checked_at=load(root/'final-human.json')['occurred_at'],stage='final',decision='pass',source=finalsource,quote='SYNTHETIC approve fixture final',reviewed_artifacts=[art])
    contract['decisions'].append(finaldecision);contract['content_status']='pass';save('review.json',contract)
    manifest['run_scope']='delivery-candidate';save('visual.json',dict(schema_version='2.6.0',run_id=manifest['run_id'],run_scope='delivery-candidate',units=[unit]))
    for key in ['brief_evidence','direction_cards','concept_gate','official_asset_manifest','human_visual_review']:manifest['artifacts'][key]=key+'.json';save(key+'.json',dict(boundary='SYNTHETIC fixture evidence',evidence=[]))
    manifest['artifacts'].update(run_status='status.json',technical_validation='technical.json',delivery_manifest='delivery.json')
    save('status.json',dict(content_review_status='pass',review_decision_ids=[finaldecision['id']],method_run_complete=True))
    save('technical.json',dict(technical_validation_status='pass',failure_names=[],files=[dict(path=str(root/'art.png'),sha256=art['sha256'])],boundary='SYNTHETIC technical result tests record consumption; not a print specification certification.'))
    save('delivery.json',dict(delivered_at=now(),final_artifacts=[member]))
    save('gates.json',dict(document_type='gate-results',schema_version='0.1.0',definition_set_id=gates['definition_set_id'],track='print-ad',run_id=manifest['run_id'],results=[dict(gate_id=g['gate_id'],status='pass',passed_check_ids=[c['check_id'] for c in g['checks']],failed_check_ids=[],boundaries=[],waiver_reason=None,checked_at=now(),reviewers=[dict(type='human',id='SYNTHETIC-reviewer'),dict(type='machine',id='SYNTHETIC-checker')],evidence_paths=['compare.json']) for g in gates['gates']]))
    supplyreview=save('external-review.json',dict(status='pass',scope='delivery-candidate',assets=[supplied],observation='SYNTHETIC supplied bitmap decoded'))
    manifest['visual_generation_capability']=dict(status='unavailable',provider=None,operations=[],checked_at=now(),evidence='SYNTHETIC local supplied pixels; no generation invoked',user_decision='use-external-assets',impact_acknowledged=True,external_supply=dict(kind='provided-assets',status='ready',scope='delivery-candidate',evidence='SYNTHETIC supplied fixture bitmap',assets=[supplied],review=supplyreview))
    save('manifest.json',manifest)
    cli('unified-check','validate_run.py',['--run-dir',root,'--manifest','manifest.json','--output','unified.json'])
    check=load(root/'unified.json');assert check['technical_pass'] and check['content_pass'] and not check['delivery_complete'],check
    validate_current(root,manifest,contract);stages.append(dict(stage='current-artwork',passed=True))
    cli('export','export_current_artwork.py',['--run-dir',root,'--manifest','manifest.json','--destination','export'])
    readiness=load(SKILL/'references/templates/submission-readiness.template.json');readiness.update(run_id=manifest['run_id'],track='print-ad',competition='academy-award',method_scope='artwork-delivery')
    readiness['rule_verification']=dict(status='verified-current',source_url='https://example.com/synthetic-rules',checked_at=now(),evidence_path='brief.txt')
    readiness['citations']=dict(status='not-applicable',open_items=[],rationale='SYNTHETIC no external research claims')
    save('readiness-input.json',readiness)
    cli('prepare-delivery','prepare_handoff.py',['--run-dir',root,'--manifest','manifest.json','--output-dir','handoff','--readiness-input','readiness-input.json'])
    cli('unified-delivery','validate_run.py',['--run-dir',root,'--manifest','manifest.json','--handoff','handoff/handoff.json','--output','delivery-check.json'])
    check=load(root/'delivery-check.json');assert check['delivery_complete'] and check['content_pass'] and check['technical_pass'] and not check['submission_ready'],check
    report=dict(status='passed',boundary=seed['boundary'],contracts=dict(direction=dc,core=cc,product='print-product-v3',visual='2.6.0',gates=gates['definition_set_id']),stages=stages,delivery_complete=True,image_generation_calls=0,real_approval_created=False)
    save('pipeline-result.json',report);print(json.dumps({k:report[k] for k in ['status','contracts','delivery_complete','image_generation_calls']},ensure_ascii=False));return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);args=p.parse_args();run_pipeline(args.output_dir)

if __name__=='__main__':main()
