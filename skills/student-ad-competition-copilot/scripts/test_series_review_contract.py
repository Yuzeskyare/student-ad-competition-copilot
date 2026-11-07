"""SYNTHETIC transition tests; no real approval or artwork quality is certified."""
import copy
import json
import sys
from pathlib import Path
from PIL import Image
from review_contract import digest, load
from workflow_runtime import now, receipt, check_entries
from series_review_contract import (CHECKS, GATE, current_members, prepare_review,
                                    decide_review, content_check, review_result)
from quality_gate_contract import validate_quality_gate_results
from validate_run import required_content_checks


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    cases = []
    def ref(p):
        return dict(path=p, sha256=digest(root/p))
    def save(p, obj):
        (root/p).parent.mkdir(parents=True, exist_ok=True)
        (root/p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
        return ref(p)
    def check(name, actual):
        assert actual, name
        cases.append(dict(name=name, passed=True))
    def rejects(name, fn):
        try:
            fn()
        except (ValueError, KeyError, TypeError):
            check(name, True)
        else:
            raise AssertionError(name)
    definitions = load(Path(__file__).resolve().parents[1]/'references/tracks/print-ad/quality-gates.json')
    gates = dict(document_type='gate-results', schema_version='0.1.0', definition_set_id=definitions['definition_set_id'],
                 track='print-ad', run_id='SYNTHETIC-series', results=[dict(gate_id=g['gate_id'], status='not-run',
                 passed_check_ids=[], failed_check_ids=[], reviewers=[], evidence_paths=[], boundaries=[],
                 checked_at=None, waiver_reason=None) for g in definitions['gates']])
    save('gates.json', gates)
    rows = []
    for i in range(3):
        p=f'{i}.png';Image.new('RGB',(8,8),(i*60,50,80)).save(root/p)
        art=dict(**ref(p),version='SYNTHETIC-v1',units=[str(i)])
        rows.append(dict(id=str(i),artifact=art,observed_image=ref(p),answers={'SYNTHETIC-all-single-checks': True}))
    sheet=Image.new('RGB',(24,8))
    for i in range(3):
        with Image.open(root/f'{i}.png') as im:
            sheet.paste(im,(i*8,0))
    sheet.save(root/'sheet.png')
    m=dict(schema_version='0.4.0',category='print-ad',series_mode='series',run_scope='production-candidate',
           run_id='SYNTHETIC-series',series_plan=dict(mode='series',units=['0','1','2']),
           core_creative_review=dict(current_assessment_ids=['0','1','2'],assessments=rows),
           artifacts=dict(quality_gate_results='gates.json'))
    base=save('manifest.json',m)
    check('all-single-passes-do-not-pass-series',not content_check(root,m)['passed'])
    check('series-is-required-for-content-pass','series-increment-evidence' in required_content_checks(m))
    fake=copy.deepcopy(gates)
    gate=next(g for g in fake['results'] if g['gate_id']==GATE)
    gate.update(status='pass',passed_check_ids=list(CHECKS),reviewers=[dict(type='human',id='SYNTHETIC')],
                checked_at=now(),evidence_paths=['single-review.json'])
    save('single-review.json',dict(answers={'all':True}));save('fake-gates.json',fake)
    checks=validate_quality_gate_results(root,root/'fake-gates.json','print-ad',m['run_id'],{GATE},manifest=m)
    check('single-report-cannot-satisfy-series-gate',any(not c['passed'] for c in checks))
    checks=validate_quality_gate_results(root,root/'fake-gates.json','print-ad',m['run_id'],{GATE})
    check('no-manifest-context-cannot-pass',any(not c['passed'] for c in checks))
    for stage in ['series-reviewed','content-pass','anything-approved']:
        out=receipt(root,'manifest.json',stage)
        check('free-stage-'+stage,out['stage']=='series-unreviewed' and not out['series_review']['passed'])
    first=copy.deepcopy(m);first['core_creative_review']['current_assessment_ids']=['0']
    check('first-member-stays-work-in-progress',content_check(root,first)['evidence']['status']=='members-in-progress')
    members,_=current_members(root,m)
    matrix=dict(kind='series-invariant-variable-increment-matrix-v1',observer_type='author',members=members,
                observations=[dict(unit=a['unit'],visible_relation='SYNTHETIC relation',increment='SYNTHETIC increment',
                    pixel_evidence='SYNTHETIC pixel evidence',compared_with=[b['unit'] for b in members if b!=a]) for a in members],
                checks={k:dict(status='supported',observation='SYNTHETIC group observation') for k in CHECKS})
    matrixref=save('matrix.json',matrix)
    rejects('single-report-as-matrix-rejected',lambda:prepare_review(root,base,ref('sheet.png'),ref('single-review.json')))
    ready=prepare_review(root,base,matrix=matrixref);pending=load(root/ready['manifest']['path'])
    check('prepared-without-human-is-pending',content_check(root,pending)['evidence']['status']=='awaiting-human')
    check('pending-not-content-pass',not content_check(root,pending)['passed'])
    check('group-ready-can-be-presented',receipt(root,ready['manifest']['path'],'reviewed')['stage']=='series-awaiting-human')
    checks_ok={k:dict(passed=True,observation='SYNTHETIC explicit human scope') for k in CHECKS}
    source=save('human.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-NOT-REAL',
                 text='SYNTHETIC pass current group',occurred_at=now(),reviewed_series=ready['review']))
    approved=decide_review(root,ready['manifest'],source,'SYNTHETIC pass current group',checks_ok)
    final=load(root/approved['manifest']['path'])
    check('bound-group-decision-passes',content_check(root,final)['passed'])
    check('one-human-decision-record',load(root/final['series_review']['path'])['decision']['source']==source)
    for name, mutation in [
        ('missing-member',lambda x:x['core_creative_review'].update(current_assessment_ids=['0','1'])),
        ('reordered-members',lambda x:x['series_plan'].update(units=['2','1','0'])),
        ('removed-revision-record',lambda x:x.pop('series_review')),
    ]:
        changed=copy.deepcopy(final);mutation(changed)
        check(name,not content_check(root,changed)['passed'])
    out=receipt(root,approved['manifest']['path'],'approved')
    original=(root/'1.png').read_bytes();(root/'1.png').write_bytes(b'SYNTHETIC changed image')
    check('changed-image-hash-rejected',not content_check(root,final)['passed'])
    rejects('stale-current-pointer-rejected',lambda:check_entries(root))
    (root/'1.png').write_bytes(original)
    concern=copy.deepcopy(matrix);concern['checks']['information-increment']['status']='concern'
    concernref=save('concern.json',concern)
    ready2=prepare_review(root,base,matrix=concernref)
    check('model-concern-not-automatic-human-failure',ready2['result']['status']=='awaiting-human')
    source2=save('human2.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-2',
        text='SYNTHETIC group is repetitive',occurred_at=now(),reviewed_series=ready2['review']))
    failchecks=copy.deepcopy(checks_ok);failchecks['information-increment']=dict(passed=False,observation='SYNTHETIC same relation')
    failed=decide_review(root,ready2['manifest'],source2,'SYNTHETIC group is repetitive',failchecks)
    check('human-group-failure-retained-despite-single-passes',failed['result']['status']=='fail')
    check('group-failure-blocks-content',not content_check(root,load(root/failed['manifest']['path']))['passed'])
    later=save('later-human.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-later',
        text='SYNTHETIC accept after considering the concern',occurred_at=now(),reviewed_series=ready2['review']))
    reconsidered=decide_review(root,failed['manifest'],later,'SYNTHETIC accept after considering the concern',checks_ok)
    check('model-concern-does-not-override-human-judgment',reconsidered['result']['status']=='pass')
    check('adverse-history-and-model-observation-preserved',load(root/failed['review']['path'])['decision']['checks']['information-increment']['passed'] is False
          and load(root/concernref['path'])['checks']['information-increment']['status']=='concern')
    stale_matrix=copy.deepcopy(final);stale_matrix['series_review']=matrixref
    check('matrix-alone-is-not-a-group-decision',not content_check(root,stale_matrix)['passed'])
    badsource=save('wrong-scope.json',dict(actor_type='human',kind='user-message',event_id='SYNTHETIC-3',
        text='SYNTHETIC pass',occurred_at=now(),reviewed_series=base))
    rejects('wrong-human-scope-rejected',lambda:decide_review(root,ready['manifest'],badsource,'SYNTHETIC pass',checks_ok))
    single=copy.deepcopy(m);single['series_mode']='single'
    check('single-mode-unaffected',content_check(root,single)['passed'])
    rejects('completed-still-requires-full-delivery',lambda:receipt(root,approved['manifest']['path'],'completed'))
    report=dict(status='passed',boundary='SYNTHETIC tests, no real approval or creativity certification',cases=cases)
    save('result.json',report)
    print(json.dumps(dict(status='passed',checks=len(cases)),ensure_ascii=False))


if __name__=='__main__':
    run(Path(sys.argv[1]).resolve())
