"""Atomic run/scope reservations; reconcile actual lifecycle, never infer prompt intent."""
from contextlib import contextmanager
import hashlib
import json
import os
import time
import errno
from datetime import datetime, timezone
from review_contract import inside, load, bound_file, timestamp, digest


@contextmanager
def run_lock(root, run_id):
    path=inside(root,'standard-dispatch-intents/'+hashlib.sha256(run_id.encode()).hexdigest()+'.lock')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if not stream.tell(): stream.write(b'0');stream.flush()
        stream.seek(0)
        deadline=time.monotonic()+10
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES,errno.EAGAIN,errno.EDEADLK} or time.monotonic()>=deadline:
                    raise
                time.sleep(0.05)
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def check_scope(root, manifest, request):
    from execution_contract import validate_events
    from review_contract import cancelled_requests
    from standard_production_entry import existing_intent
    contract=load(inside(root,manifest['review_contract']))
    current={r['sha256']:load(bound_file(root,r)) for r in contract['production_requests']}
    events=validate_events(root,contract)
    cancelled=cancelled_requests(root,contract)
    for path in sorted(inside(root,'standard-dispatch-intents').glob('*.json')):
        record=load(path)
        if record.get('run_id')!=manifest['run_id']:continue
        if 'request' in record:
            old=record['request'];old_ref={'sha256':record['request_sha256']}
        else:
            saved=load(bound_file(root,record['checked']['manifest']))
            old_contract=load(inside(root,saved['review_contract']))
            matches=[r for r in old_contract['production_requests'] if load(bound_file(root,r))['id']==record['request_id']]
            if len(matches)!=1:raise ValueError('Unresolved dispatch intent has ambiguous original request')
            old_ref=matches[0];old=load(bound_file(root,old_ref))
        if not set(old['output_scope']) & set(request['output_scope']):continue
        # Same ID stays single-use. Changed IDs must retain the original state chain.
        if old['id']==request['id']:raise existing_intent(root,path)
        # A reserved local guard owns its receipt. Read its actual terminal state
        # even when this caller supplied an older snapshot; never guess completion.
        local_path=record['checked'].get('receipt_path')
        local_started=False
        if local_path:
            receipt_file=inside(root,local_path)
            receipt=load(receipt_file) if receipt_file.exists() else {}
            local_started=bool(receipt.get('action_started_at') or receipt.get('executed') is True or receipt.get('production_state') in {'running','completed','failed'})
            from execution_contract import package_checker_hashes
            expected=dict(profile='package-guard-v1',entrypoint='scripts/guard_production.py',checker_sha256=package_checker_hashes())
            if (receipt.get('request_sha256')==old_ref['sha256'] and receipt.get('request')==old
                    and receipt.get('request_id')==old['id'] and receipt.get('run_id')==manifest['run_id']
                    and receipt.get('dispatch_checked') is True and receipt.get('status')=='authorized'
                    and receipt.get('guard_identity')==expected
                    and receipt.get('production_state') in {'completed','failed'}
                    and timestamp(receipt.get('action_finished_at'))>=timestamp(record['recorded_at'])):
                if receipt['production_state']=='completed':
                    if receipt.get('executed') is not True or receipt.get('command_returncode')!=0:
                        raise existing_intent(root,path)
                    if {r['path'] for r in receipt.get('outputs',[])}!=set(old['output_files']):
                        raise existing_intent(root,path)
                    for output in receipt['outputs']:bound_file(root,output)
                elif type(receipt.get('command_returncode')) is not int or receipt['command_returncode']==0:
                    raise existing_intent(root,path)
                continue
        if current.get(old_ref['sha256'])!=old:raise existing_intent(root,path)
        event=events.get(old_ref['sha256'])
        resolved=bool(event and event['state'] in {'saved','failed'} and timestamp(event['occurred_at'])>=timestamp(record['recorded_at']))
        cancellation=cancelled.get(old['id'])
        if cancellation and timestamp(cancellation['cancelled_at'])>=timestamp(record['recorded_at']):
            if local_started:raise existing_intent(root,path)
            if old.get('tool') == 'image_gen.imagegen' and not resolved:
                # No supported native non-execution trace adapter exists. A
                # cancellation plus an author-written host_event_id cannot
                # prove that an unknown provider call never ran.
                raise existing_intent(root,path)
            # A narrative cancellation is not evidence that an unknown native call never ran.
            evidence=load(bound_file(root,cancellation.get('not_executed_evidence')))
            resolved=(evidence.get('request_sha256')==old_ref['sha256'] and evidence.get('executed') is False
                      and evidence.get('dispatch_intent')==dict(path=path.relative_to(root).as_posix(),sha256=digest(path))
                      and timestamp(record['recorded_at'])<=timestamp(evidence.get('occurred_at'))<=timestamp(cancellation['cancelled_at'])<=datetime.now(timezone.utc)
                      and isinstance(evidence.get('host_event_id'),str) and bool(evidence['host_event_id'].strip()))
        if not resolved:raise existing_intent(root,path)


def reserve(root, manifest, request, path, record):
    from standard_production_entry import existing_intent
    with run_lock(root,manifest['run_id']):
        check_scope(root,manifest,request)
        contract=load(inside(root,manifest['review_contract']))
        matches=[r for r in contract['production_requests'] if load(bound_file(root,r))==request]
        if len(matches)!=1:raise ValueError('Reserved request must bind one registered immutable request')
        record=dict(record,request=request,request_sha256=matches[0]['sha256'])
        try:
            with path.open('x',encoding='utf-8') as stream:
                json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        except FileExistsError:raise existing_intent(root,path)
