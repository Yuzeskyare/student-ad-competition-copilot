"""Batch ordinary direction checks, one exact group decision, member claim locks."""
import argparse
import copy
import json
from pathlib import Path
from review_contract import inside, load, bound_file, human_source, timestamp
from review_workflow import allocate, write, error
from workflow_runtime import now, semantics


def checked_recommendation(root, manifest):
    """Project only the manifest's validated, bound independent direction return."""
    from validate_print_ad_run import validate_direction_blind_review
    current=load(bound_file(root,manifest))
    check=validate_direction_blind_review(root,current,pending_selection=True)
    if not check['passed']:error('manifest.direction_adoption',check['evidence'],'ordinary independent direction check before recommendation')
    adoption=current['direction_adoption']
    bundle=load(bound_file(root,adoption['blind_review']))
    last=load(bound_file(root,bundle['rounds'][-1]))
    candidates=json.loads(bound_file(root,last['inputs'][0]['file']).read_text(encoding='utf-8'))
    choice=load(bound_file(root,adoption['choice_list']))
    return dict(evidence=check['evidence'],all_weak=last['result']['all_weak'],choice_rows=choice['rows'],user_facing_copy=choice['user_facing_copy'],
                recommendations=recommendation(candidates,last['result'],{x['direction_id']:x for x in bundle['origins']}))


def prepare(root, members, plan):
    if plan!=semantics(plan):error('series_plan',plan,'immutable members/directions/copy/mechanism; move status to run-status')
    if not members or len({m['unit'] for m in members})!=len(members) or [m['unit'] for m in members]!=plan['units']:
        error('members',members,'one manifest per series_plan.units, in exact order')
    checked=[]
    for member in members:
        original=load(bound_file(root,member['manifest']))
        old=semantics(original.get('series_plan',{}))
        role=lambda p: [r for r in p.get('member_roles',[]) if r.get('unit')==member['unit']]
        if old.get('shared_mechanism') != plan.get('shared_mechanism') or role(old) != role(plan):
            error('series_plan.mechanism/member_role',member['unit'],'recheck materially changed direction/member through existing workflow before preparing this batch; do not reuse obsolete review')
        result=checked_recommendation(root,member['manifest'])
        checked.append(dict(unit=member['unit'],manifest=member['manifest'],direction_id=result['evidence']['winner'],
                            recommendations=result['recommendations'],all_weak=result['all_weak'],choice_rows=result['choice_rows'],user_facing_copy=result['user_facing_copy'],**result['evidence']))
    path=allocate(root,'series-plan')
    text='整组方向检查；以下顺序和原句需由同一条真实用户消息一次确认。\n'
    text+='\n系列计划（含画风、机制、成员及顺序）：\n'+json.dumps(plan,ensure_ascii=False,indent=2)+'\n'
    for member in checked:
        text+='\n'+member['unit']+' | '+member['statement']+'\n'+json.dumps(member['judgment'],ensure_ascii=False)+'\n'+json.dumps(member['recommendations'],ensure_ascii=False)+'\n'
        text+='\n原已审核选择清单（含全部提示和去重项）：\n'+bound_file(root,member['user_facing_copy']).read_text(encoding='utf-8')+'\n'
    shown=write(root,path/'choices.md',text,True)
    batch=dict(kind='series-direction-batch-v2',plan=plan,members=checked,presented_at=now(),user_facing_copy=shown)
    return write(root,path/'batch.json',batch)


def confirm(root, batch_ref, source_ref, quote, overrides=None):
    from validate_print_ad_run import validate_direction_blind_review, claim_digest
    batch=load(bound_file(root,batch_ref));bound_file(root,batch['user_facing_copy'])
    if batch['kind'] not in {'series-direction-batch-v1','series-direction-batch-v2'}:error('batch.kind',batch['kind'],'prepare result')
    at=human_source(root,source_ref,quote)
    if not timestamp(batch['presented_at'])<=at:error('source.time',str(at),'real group user message after batch presentation')
    # AI resolves the reply's scope; bind the presented batch, not repeated words.
    source=load(bound_file(root,source_ref))
    if source.get('reviewed_batch')!=batch_ref:
        error('source.reviewed_batch',source.get('reviewed_batch'),'exact presented batch interpreted from the conversation')
    overrides=overrides or []
    if set(overrides)-{m['unit'] for m in batch['members']}:error('overrides',overrides,'batch member unit IDs only')
    from method_usage_contract import validate_usage
    for member in batch['members']:
        validate_usage(root,load(bound_file(root,member['manifest'])))
        check=validate_direction_blind_review(root,load(bound_file(root,member['manifest'])),pending_selection=True)
        if not check['passed'] or check['evidence']!={k:member[k] for k in check['evidence']}:
            error('member.'+member['unit'],check,'unchanged checked member before group transaction')
        judgment=member['judgment']
        if (judgment['trope_screen']['is_trope'] or bool(judgment['trope_screen']['counterexample_matches']) or not judgment['drawability']['drawable']) and member['unit'] not in overrides:
            error('user_override',member['unit'],'explicit informed choice before group transaction')
    path=allocate(root,'series-confirmed');outputs=[]
    for member in batch['members']:
        m=copy.deepcopy(load(bound_file(root,member['manifest'])))
        check=validate_direction_blind_review(root,m,pending_selection=True)
        if not check['passed'] or check['evidence']!={k:member[k] for k in check['evidence']}:
            error('member.'+member['unit'],check,'unchanged checked member; reopen only materially changed/new hard-risk member')
        m['series_plan']=copy.deepcopy(batch['plan'])
        m['series_mode']=batch['plan']['mode']
        m.pop('delivery_scope_selection',None)
        m['series_direction_batch']=dict(batch=batch_ref,unit=member['unit'],commit_path=(path/'confirmed.json').relative_to(root).as_posix())
        selection=dict(kind='user-choice',actor='user',direction_id=member['direction_id'],decided_at=at.isoformat(),statement=quote,source=source_ref)
        judgment=member['judgment']; needs=judgment['trope_screen']['is_trope'] or bool(judgment['trope_screen']['counterexample_matches']) or not judgment['drawability']['drawable']
        if needs:
            if member['unit'] not in overrides:error('user_override',member['unit'],'explicit informed risk choice in group source and overrides')
            # overrides records AI-interpreted informed choices, not keyword hits.
            selection.update(user_override=True,override_judgment=judgment)
        adoption=m['direction_adoption'];adoption.update(selection_mode='user',adopted_at=now())
        ident=str(len(outputs)+1)
        adoption['selection_record']=write(root,path/(ident+'-selection.json'),selection)
        lock=dict(direction_id=member['direction_id'],statement=member['statement'],statement_sha256=claim_digest(member['statement']),
                  adopted_at=adoption['adopted_at'],blind_review=adoption['blind_review'])
        adoption['claim_lock']=write(root,path/(ident+'-claim-lock.json'),lock)
        # Internal preparation validates ordinary evidence, but grants no admission.
        # Every external consumer requires the final atomic commit below.
        result=validate_direction_blind_review(root,m,_preparing_group=True)
        if not result['passed']:error('member.'+member['unit'],result['evidence'],'normal post-decision direction validation')
        outputs.append(dict(unit=member['unit'],manifest=write(root,path/(ident+'-manifest.json'),m),selection=adoption['selection_record'],claim_lock=adoption['claim_lock']))
    value=dict(kind='series-confirmation-commit-v1',batch=batch_ref,source=source_ref,quote=quote,members=outputs,plan=batch['plan'],confirmed_at=now())
    # Failed/interrupted writes leave only uncommitted, non-admissible records.
    staged=path/'confirmation-pending.json'
    write(root,staged,value)
    staged.replace(path/'confirmed.json')
    from review_contract import digest
    return dict(path=(path/'confirmed.json').relative_to(root).as_posix(),sha256=digest(path/'confirmed.json'))


def recommendation(candidates, result, provenance):
    """Four parallel explanations, never an eligibility score or ranking rewrite."""
    rows=[]
    by_id={x['direction_id']:x for x in candidates}
    for rank in result['ranking']:
        ident=rank['direction_id'];candidate=by_id[ident]
        screen=next(x for x in result['trope_screen'] if x['direction_id']==ident)
        draw=next(x for x in result['drawability'] if x['direction_id']==ident)
        purpose=next((x for x in result.get('purpose_check',[]) if x['direction_id']==ident),None)
        meaning=next((x for x in result.get('product_meaning_hints',[]) if x['direction_id']==ident),None)
        rows.append(dict(direction_id=ident,statement=candidate['statement'],rank=rank,ranking_reason=rank['reason'],
             communication_clarity=dict(observation='未另测传播清晰度；产品意义观察另列，不能从新颖度、题面匹配或可画性推断清晰度'),
             product_meaning_hint=meaning,
             purpose_fit=purpose or dict(observation='未提供目的独立观察'),novelty=screen,production_risk=draw,
             source=provenance.get(ident),eligibility_unchanged=True))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True,type=Path);p.add_argument('--action',choices=['prepare','confirm','recommend','review-prepare','review-decide'],required=True)
    p.add_argument('--payload',required=True);args=p.parse_args();root=args.run_dir.resolve()
    try:
        payload=load(inside(root,args.payload))
        if args.action in {'review-prepare','review-decide'}:
            from series_review_contract import prepare_review, decide_review
            value=(prepare_review if args.action=='review-prepare' else decide_review)(root,**payload)
        else:
            value=prepare(root,**payload) if args.action=='prepare' else confirm(root,**payload) if args.action=='confirm' else checked_recommendation(root,**payload)
        print(json.dumps(dict(status='ok',result=value),ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(status='failed',reason=str(exc)),ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
