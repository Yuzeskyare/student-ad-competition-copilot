"""Mutable progress, append-only timings and one current human-readable entry."""
import json
import uuid
from datetime import datetime, timezone
from review_contract import inside, load, digest

PROGRESS_FIELDS = {'status','note','artifact','last_error'}
STATES = {'pending','in-progress','blocked','reviewed','completed'}
README = '# 当前运行\n\n唯一当前入口：[CURRENT.md](CURRENT.md)。历史回执保留在各自分支中。\n'


def current_markdown(pointer):
    return '# 当前阶段\n\n'+pointer['stage']+'\n\n[当前清单]('+pointer['manifest']+')\n\n机器指针：[CURRENT.json](CURRENT.json)\n'


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def semantics(value):
    if isinstance(value,dict):
        return {k:semantics(v) for k,v in value.items() if k not in {'status','progress','updated_at'}}
    if isinstance(value,list):
        return [semantics(v) for v in value]
    return value


def update_status(root, manifest, member, changes):
    units=manifest['series_plan']['units']
    if member not in units:
        raise ValueError(f'field=member current={member!r}; legal source=series_plan.units {units!r}')
    if not changes or set(changes)-PROGRESS_FIELDS or ('status' in changes and changes['status'] not in STATES):
        raise ValueError(f'field=changes current={changes!r}; legal fields={sorted(PROGRESS_FIELDS)!r}; status={sorted(STATES)!r}')
    path=inside(root,manifest['artifacts']['run_status'])
    status=load(path)
    status.setdefault('member_progress',{}).setdefault(member,{}).update(changes,updated_at=now())
    save(path,status)
    return dict(path=path.relative_to(root).as_posix(),sha256=digest(path),member=member,progress=status['member_progress'][member])


def timing(root, stage, phase, token=None, outcome=None, recovery_of=None):
    path=inside(root,'stage-timings.jsonl')
    rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    if phase=='start':
        token=uuid.uuid4().hex
        if recovery_of and not any(r['token']==recovery_of and r.get('outcome')=='failed' for r in rows):
            raise ValueError(f'field=recovery_of current={recovery_of!r}; legal source=failed timing token')
        row=dict(token=token,stage=stage,phase=phase,at=now(),recovery_of=recovery_of)
    else:
        starts=[r for r in rows if r['token']==token and r['phase']=='start']
        if len(starts)!=1 or starts[0]['stage']!=stage or any(r['token']==token and r['phase']=='end' for r in rows) or outcome not in {'passed','failed','cancelled'}:
            raise ValueError(f'field=token/outcome current={(token,outcome)!r}; legal source=one open same-stage start; passed/failed/cancelled')
        at=now(); seconds=(datetime.fromisoformat(at)-datetime.fromisoformat(starts[0]['at'])).total_seconds()
        row=dict(token=token,stage=stage,phase=phase,at=at,seconds=seconds,outcome=outcome,recovery_of=starts[0]['recovery_of'])
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    return row


def timing_summary(root):
    path=inside(root,'stage-timings.jsonl'); groups={}
    for row in [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []:
        if row['phase']!='end':continue
        g=groups.setdefault(row['stage'],dict(seconds=0,failed_seconds=0,recovery_seconds=0,attempts=0))
        g['seconds']+=row['seconds'];g['attempts']+=1
        if row['outcome']=='failed':g['failed_seconds']+=row['seconds']
        if row['recovery_of']:g['recovery_seconds']+=row['seconds']
    return dict(stages=groups,measurement_only=True,judgment_changed=False)


def check_artwork_review_ready(root, manifest, stage):
    if stage != 'awaiting-user-review' or manifest.get('run_scope') not in {'production-candidate', 'delivery-candidate'}:
        return
    from execution_contract import release_required
    marker = 'print-secondary-copy-v2'
    if manifest.get('category') != 'print-ad' or not (
            manifest.get('secondary_copy_contract') == marker or release_required(root, manifest)):
        return

    from core_return_contract import review_state
    from review_contract import artifact, bound_file
    from visual_review_contract import require, secondary_element_scope, validate_pack_identity
    try:
        require(manifest.get('secondary_copy_contract') == marker, 'Missing current text-role contract')
        review = review_state(root, manifest)
        ids = review.get('current_assessment_ids', [])
        rows = [row for row in review.get('assessments', []) if row['id'] in ids]
        require(ids and len(ids) == len(rows) and set(ids) == {row['id'] for row in rows},
                'Select unique current complete artwork assessments')
        expected = {}
        for row in rows:
            key, = artifact(root, row['artifact'])
            require(key not in expected and row['render_record'] in review['completed_draft_render_records'],
                    'Each current artwork needs its complete draft render')
            expected[key] = row

        pack_path = manifest['artifacts'].get('visual_review')
        require(pack_path, 'Missing visual_review text roles for the current artwork')
        pack = load(inside(root, pack_path))
        validate_pack_identity(pack, manifest)
        for unit in pack['units']:
            key, = artifact(root, unit['artifact'])
            row = expected.pop(key, None)
            require(row and unit['render_record'] == row['render_record'],
                    'Text roles must bind the exact current artwork and render')
            render = load(bound_file(root, unit['render_record']))
            require(artifact(root, render['source']) == {key} and unit['secondary_copy']['contract'] == marker,
                    'Render source or text-role contract differs from the current artwork')
            scope = secondary_element_scope(root, unit)
            require(scope['native'] == row['observed_image'], 'Text roles must bind the current native pixels')
        require(not expected, 'Every current artwork needs text-role evidence')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration, ImportError) as exc:
        raise ValueError(f'Artwork awaiting user review needs current headline evidence: {exc}') from exc


def receipt(root, manifest_path, stage, report=None, handoff=None):
    manifest=load(inside(root,manifest_path))
    from series_review_contract import applies, content_check
    series = content_check(root, manifest) if applies(manifest) else None
    # Free-form progress labels cannot confer whole-series acceptance.
    if series is not None and stage != 'completed':
        stage = 'series-' + series['evidence']['status']
    check_artwork_review_ready(root, manifest, stage)
    pointer=dict(manifest=manifest_path,manifest_sha256=digest(inside(root,manifest_path)),
                 stage=stage,report=report,updated_at=now())
    if series is not None:
        pointer['series_review'] = series
    if report:
        from review_contract import bound_file
        bound_file(root,report)
    if stage=='completed':
        from validate_run import validate
        result=validate(root,inside(root,manifest_path),handoff)
        if not result.get('delivery_complete'):
            raise ValueError('field=stage current=completed; legal source=native validate_run delivery_complete=true')
        pointer['handoff'] = dict(path=handoff, sha256=digest(inside(root, handoff)))
    readme=inside(root,'README.md')
    if readme.exists() and readme.read_text(encoding='utf-8')!=README:
        history=inside(root,'entry-history/'+uuid.uuid4().hex+'-README.md');history.parent.mkdir(parents=True,exist_ok=True)
        history.write_bytes(readme.read_bytes())
    save(inside(root,'CURRENT.json'),pointer)
    inside(root,'CURRENT.md').write_text(current_markdown(pointer),encoding='utf-8')
    readme.write_text(README,encoding='utf-8')
    check_entries(root)
    return pointer


def check_entries(root):
    pointer=load(inside(root,'CURRENT.json'))
    if inside(root,'README.md').read_text(encoding='utf-8')!=README or inside(root,'CURRENT.md').read_text(encoding='utf-8')!=current_markdown(pointer):
        raise ValueError('Human entry conflicts with unique CURRENT pointer')
    if digest(inside(root,pointer['manifest']))!=pointer['manifest_sha256']:
        raise ValueError('CURRENT manifest changed; write a new stage receipt')
    if pointer.get('stage') == 'awaiting-user-review':
        check_artwork_review_ready(root, load(inside(root, pointer['manifest'])), pointer['stage'])
    if pointer.get('report'):
        from review_contract import bound_file
        bound_file(root, pointer['report'])
    if pointer.get('stage') == 'completed':
        from review_contract import bound_file
        from validate_run import validate
        handoff = pointer.get('handoff')
        if not handoff:
            raise ValueError('CURRENT completed receipt lacks handoff binding; revalidate and write a new receipt')
        bound_file(root, handoff)
        result = validate(root, inside(root, pointer['manifest']), handoff['path'])
        if not result.get('delivery_complete'):
            raise ValueError('CURRENT completion dependencies are no longer valid; revalidate delivery before a completed receipt')
    if 'series_review' in pointer:
        from series_review_contract import content_check
        if content_check(root,load(inside(root,pointer['manifest']))) != pointer['series_review']:
            raise ValueError('CURRENT series evidence changed; recheck the actual group')
    return pointer
