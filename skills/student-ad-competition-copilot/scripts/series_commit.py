"""Admission of a complete group transaction; no partial member is a confirmation."""
from review_contract import inside, load, bound_file
import json


def validate_commit(root, manifest):
    binding=manifest.get('series_direction_batch')
    adoption=manifest.get('direction_adoption',{})
    selection=load(bound_file(root,adoption['selection_record'])) if adoption.get('selection_record') else {}
    try:
        source=load(bound_file(root,selection['source'])) if selection.get('source') else {}
    except json.JSONDecodeError:
        if binding:raise
        return  # legacy direction checks also accept original plain-text sources
    source_batch=source.get('reviewed_batch')
    batch_ref=binding.get('batch') if binding else source_batch
    if not batch_ref:return
    batch=load(bound_file(root,batch_ref))
    if not binding or source_batch!=binding['batch']:
        raise ValueError('Group selection requires its complete committed batch')
    legacy=batch.get('kind')=='series-direction-batch-v1' and not binding.get('commit_path')
    if not legacy and not binding.get('commit_path'):
        raise ValueError('Group selection requires its complete committed batch')
    # Old successful confirm() also wrote confirmed.json last. Read that actual
    # commit; version v1 alone is not proof that the group ever succeeded.
    commit_path=(inside(root,adoption['selection_record']['path']).parent/'confirmed.json').relative_to(root).as_posix() if legacy else binding['commit_path']
    commit=load(inside(root,commit_path))
    if (commit.get('kind')!=(None if legacy else 'series-confirmation-commit-v1') or commit.get('batch')!=batch_ref
            or commit.get('source')!=selection['source'] or commit.get('plan')!=batch['plan']
            or [m['unit'] for m in commit.get('members',[])]!=[m['unit'] for m in batch['members']]):
        raise ValueError('Incomplete or foreign series confirmation commit')
    found=False
    for member in commit['members']:
        saved=load(bound_file(root,member['manifest']))
        expected_binding=dict(batch=batch_ref,unit=member['unit'])
        if not legacy:expected_binding['commit_path']=commit_path
        if (saved.get('series_direction_batch')!=expected_binding
                or saved.get('series_plan')!=batch['plan'] or saved.get('series_mode')!=batch['plan']['mode']
                or saved['direction_adoption']['selection_record']!=member['selection']
                or saved['direction_adoption']['claim_lock']!=member['claim_lock']):
            raise ValueError('Committed group member binding differs')
        bound_file(root,member['selection']);bound_file(root,member['claim_lock'])
        if member['unit']==binding['unit']:
            found=True
            for key in ('selected_direction','direction_adoption','series_direction_batch','series_plan','series_mode'):
                if manifest.get(key)!=saved.get(key):raise ValueError('Current adoption differs from committed member: '+key)
    if not found:raise ValueError('Member missing from complete group commit')
