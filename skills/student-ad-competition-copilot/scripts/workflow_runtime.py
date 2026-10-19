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


def receipt(root, manifest_path, stage, report=None, handoff=None):
    manifest=load(inside(root,manifest_path))
    pointer=dict(manifest=manifest_path,manifest_sha256=digest(inside(root,manifest_path)),
                 stage=stage,report=report,updated_at=now())
    if report:
        from review_contract import bound_file
        bound_file(root,report)
    if stage=='completed':
        from validate_run import validate
        result=validate(root,inside(root,manifest_path),handoff)
        if not result.get('delivery_complete'):
            raise ValueError('field=stage current=completed; legal source=native validate_run delivery_complete=true')
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
    return pointer
