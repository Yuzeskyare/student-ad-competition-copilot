"""Batch ordinary direction checks, one exact group decision, member claim locks."""
import argparse
import copy
import json
from pathlib import Path
from review_contract import inside, load, bound_file, human_source, timestamp
from review_workflow import allocate, write, error
from workflow_runtime import now, semantics


def prepare(root, members, plan):
    from validate_print_ad_run import validate_direction_blind_review
    if plan!=semantics(plan):error('series_plan',plan,'immutable members/directions/copy/mechanism; move status to run-status')
    if not members or len({m['unit'] for m in members})!=len(members) or [m['unit'] for m in members]!=plan['units']:
        error('members',members,'one manifest per series_plan.units, in exact order')
    checked=[]
    for member in members:
        manifest=load(bound_file(root,member['manifest']))
        result=validate_direction_blind_review(root,manifest,pending_selection=True)
        if not result['passed']:error('member.'+member['unit'],result['evidence'],'ordinary independent direction check')
        evidence=result['evidence']
        bundle=load(bound_file(root,manifest['direction_adoption']['blind_review']))
        last=load(bound_file(root,bundle['rounds'][-1]))
        candidates=json.loads(bound_file(root,last['inputs'][0]['file']).read_text(encoding='utf-8'))
        explanation=recommendation(candidates,last['result'],{x['direction_id']:x for x in bundle['origins']})
        checked.append(dict(unit=member['unit'],manifest=member['manifest'],direction_id=manifest['selected_direction'],recommendations=explanation,**evidence))
    path=allocate(root,'series-plan')
    text='整组方向检查；以下顺序和原句需由同一条真实用户消息一次确认。\n'
    for member in checked:
        text+='\n'+member['unit']+' | '+member['statement']+'\n'+json.dumps(member['judgment'],ensure_ascii=False)+'\n'+json.dumps(member['recommendations'],ensure_ascii=False)+'\n'
    shown=write(root,path/'choices.md',text,True)
    batch=dict(kind='series-direction-batch-v1',plan=plan,members=checked,presented_at=now(),user_facing_copy=shown)
    return write(root,path/'batch.json',batch)


def confirm(root, batch_ref, source_ref, quote, overrides=None):
    from validate_print_ad_run import validate_direction_blind_review, claim_digest
    batch=load(bound_file(root,batch_ref));bound_file(root,batch['user_facing_copy'])
    if batch['kind']!='series-direction-batch-v1':error('batch.kind',batch['kind'],'prepare result')
    at=human_source(root,source_ref,quote)
    if not timestamp(batch['presented_at'])<=at:error('source.time',str(at),'real group user message after batch presentation')
    # Require precise members, exact sentences AND their sequence in the message.
    cursor=0
    for member in batch['members']:
        text=member['unit']+' | '+member['statement']
        index=quote.find(text,cursor)
        if index<0:error('quote',quote,'ordered exact lines: unit | statement from batch')
        cursor=index+len(text)
    overrides=overrides or []
    if set(overrides)-{m['unit'] for m in batch['members']}:error('overrides',overrides,'batch member unit IDs only')
    path=allocate(root,'series-confirmed');outputs=[]
    for member in batch['members']:
        m=copy.deepcopy(load(bound_file(root,member['manifest'])))
        check=validate_direction_blind_review(root,m,pending_selection=True)
        if not check['passed'] or check['evidence']!={k:member[k] for k in check['evidence']}:
            error('member.'+member['unit'],check,'unchanged checked member; reopen only materially changed/new hard-risk member')
        selection=dict(kind='user-choice',actor='user',direction_id=member['direction_id'],decided_at=at.isoformat(),statement=quote,source=source_ref)
        judgment=member['judgment']; needs=judgment['trope_screen']['is_trope'] or bool(judgment['trope_screen']['counterexample_matches']) or not judgment['drawability']['drawable']
        if needs:
            if member['unit'] not in overrides:error('user_override',member['unit'],'explicit informed risk choice in group source and overrides')
            if '知悉' not in quote and 'risk' not in quote.lower():error('quote.risk',quote,'explicit informed risk acknowledgement')
            selection.update(user_override=True,override_judgment=judgment)
        adoption=m['direction_adoption'];adoption.update(selection_mode='user',adopted_at=now())
        ident=str(len(outputs)+1)
        adoption['selection_record']=write(root,path/(ident+'-selection.json'),selection)
        lock=dict(direction_id=member['direction_id'],statement=member['statement'],statement_sha256=claim_digest(member['statement']),
                  adopted_at=adoption['adopted_at'],blind_review=adoption['blind_review'])
        adoption['claim_lock']=write(root,path/(ident+'-claim-lock.json'),lock)
        result=validate_direction_blind_review(root,m)
        if not result['passed']:error('member.'+member['unit'],result['evidence'],'normal post-decision direction validation')
        outputs.append(dict(unit=member['unit'],manifest=write(root,path/(ident+'-manifest.json'),m),selection=adoption['selection_record'],claim_lock=adoption['claim_lock']))
    return write(root,path/'confirmed.json',dict(batch=batch_ref,source=source_ref,quote=quote,members=outputs,plan=batch['plan'],confirmed_at=now()))


def recommendation(candidates, result, provenance):
    """Four parallel explanations, never an eligibility score or ranking rewrite."""
    rows=[]
    for candidate in candidates:
        ident=candidate['direction_id']
        rank=next(x for x in result['ranking'] if x['direction_id']==ident)
        screen=next(x for x in result['trope_screen'] if x['direction_id']==ident)
        draw=next(x for x in result['drawability'] if x['direction_id']==ident)
        purpose=next((x for x in result.get('purpose_check',[]) if x['direction_id']==ident),None)
        clarity=next((x for x in result.get('product_meaning_hints',[]) if x['direction_id']==ident),None)
        rows.append(dict(direction_id=ident,statement=candidate['statement'],rank=rank,
             communication_clarity=clarity or dict(observation='未另测清晰度；不能从新颖度推断清晰度'),
             purpose_fit=purpose or dict(observation='未提供目的独立观察'),novelty=screen,production_risk=draw,
             source=provenance.get(ident),eligibility_unchanged=True))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True,type=Path);p.add_argument('--action',choices=['prepare','confirm','recommend'],required=True)
    p.add_argument('--payload',required=True);args=p.parse_args();root=args.run_dir.resolve()
    try:
        payload=load(inside(root,args.payload))
        value=prepare(root,**payload) if args.action=='prepare' else confirm(root,**payload) if args.action=='confirm' else recommendation(**payload)
        print(json.dumps(dict(status='ok',result=value),ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(status='failed',reason=str(exc)),ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
