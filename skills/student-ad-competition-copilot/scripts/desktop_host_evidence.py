"""Read native Desktop rollout completion evidence; never invent a time chain."""
import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path, PureWindowsPath, PurePosixPath


def completed_image_event(root, binding, request):
    from review_contract import bound_file, digest, timestamp
    from execution_contract import require

    require(request.get('operation') == 'external', 'Desktop evidence needs an external request')
    call_id = binding['call_id']
    rollout = bound_file(root, binding.get('evidence'))
    meta = None
    matches = []
    invocations = []
    with rollout.open(encoding='utf-8-sig') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('type') == 'session_meta':
                require(meta is None, 'Duplicate desktop session metadata')
                meta = row.get('payload', {})
            payload = row.get('payload', {})
            if (row.get('type') == 'response_item' and payload.get('type') == 'function_call'
                    and payload.get('call_id') == call_id):
                invocations.append((row, payload))
            item = payload.get('item', {})
            if (row.get('type') == 'event_msg' and payload.get('type') == 'item_completed'
                    and item.get('type') == 'Extension' and item.get('kind') == 'image_gen.generation'
                    and item.get('id') == call_id):
                matches.append((row, payload, item))
    require(meta is not None and meta.get('originator') in {'Codex Desktop', 'codex_work_desktop'} and meta.get('source') == 'vscode',
            'Missing native Codex Desktop session metadata')
    require(len(matches) == 1, 'Desktop image call ID must identify one native completion event')
    require(len(invocations) <= 1, 'Desktop call ID has duplicate native invocation records')
    arguments = request.get('parameters')
    invocation_row = None
    if invocations:
        invocation_row, invocation = invocations[0]
        require(invocation.get('name') in {'image_gen.imagegen', 'image_gen__imagegen'},
                'Desktop invocation is not the requested image tool')
        actual = invocation.get('arguments')
        actual = json.loads(actual) if isinstance(actual, str) else actual
        require(actual == arguments, 'Desktop invocation parameters differ from the guarded request')
    from standard_production_entry import intent_path, content_parameters, validate_parameters
    from review_contract import load
    content_parameters(request)  # Requires the entry-generated nonce in actual parameters.
    intent = load(intent_path(root, {'run_id': request.get('run_id')}, request['id'])) if request.get('run_id') else None
    # Requests historically need not carry run_id: recover it from the bound
    # standard intent, never from author-added completion-envelope metadata.
    if intent is None:
        candidates = [load(p) for p in (root/'standard-dispatch-intents').glob('*.json')]
        candidates = [r for r in candidates if r.get('request_sha256') == binding['request_sha256']]
        require(len(candidates) == 1, 'Native completion needs one registered standard dispatch intent')
        intent = candidates[0]
    require(intent.get('kind') == 'standard-dispatch-intent' and intent.get('request') == request
            and intent.get('request_sha256') == binding['request_sha256'], 'Native completion differs from dispatch intent')
    checked = intent['checked']
    manifest = load(bound_file(root, checked['manifest']))
    receipt = load(bound_file(root, checked['receipt']))
    require(manifest.get('run_id') == intent.get('run_id') and receipt.get('request') == request
            and receipt.get('request_sha256') == binding['request_sha256']
            and receipt.get('status') == 'authorized' and receipt.get('dispatch_checked') is True
            and checked.get('parameters') == arguments and checked.get('tool') == request.get('tool'),
            'Native intent does not bind the guarded request and exact parameters')
    row, payload, item = matches[0]
    # A native invocation remains authoritative when present: revisedPrompt is
    # an output and may legitimately be rewritten. When absent, this known
    # Extension shape is sufficient only if every supported parameter is proven.
    if not invocations:
        require(request.get('tool') == 'image_gen.imagegen', 'Unknown native image tool')
        refs = validate_parameters(arguments)
        require(arguments.get('num_last_images_to_include') is None,
                'Recent conversation images cannot be bound from this Extension')
        require(item.get('revisedPrompt') == arguments['prompt'],
                'Native Extension prompt differs from the guarded request')
        require(isinstance(item.get('generationId'), str) and bool(item['generationId'].strip()),
                'Missing native generation ID')
    else:
        refs = arguments.get('referenced_image_paths') or []
    # Where both forms carry input/transparent evidence, verify it too. Null is
    # tolerated on the original-invocation path, whose output fields may vary.
    if not invocations or (item.get('transparentBackground') is not None
                           and arguments.get('transparent_background', False) is not None):
        require(type(item.get('transparentBackground')) is bool
                and item['transparentBackground'] == arguments.get('transparent_background', False),
                'Native Extension transparency differs from the guarded request')
    if not invocations or (item.get('inputImages') is not None
                           and arguments.get('num_last_images_to_include') is None):
        native_refs = item.get('inputImages')
        require(isinstance(native_refs, list) and len(native_refs) == len(refs),
                'Native Extension references differ from the guarded request')
        for path, native_ref in zip(refs, native_refs):
            require(isinstance(native_ref, dict) and set(native_ref) == {'path', 'sha256'}
                    and native_ref['path'] == path and Path(path).is_absolute(),
                    'Native Extension reference path or shape differs from the guarded request')
            bound = [r for r in request.get('input_files', [])
                     if bound_file(root, r) == Path(path).resolve()]
            require(len(bound) == 1 and native_ref['sha256'] == bound[0].get('sha256'),
                    'Native Extension reference bytes differ from the bound request input')
    require(bool(meta.get('id')) and payload.get('thread_id') == meta['id']
            and isinstance(payload.get('turn_id'), str) and bool(payload['turn_id'].strip()),
            'Desktop event must bind its session and turn')
    failed = item.get('status') == 'failed'
    require((item.get('status') == 'completed' and item.get('failure') is None)
            or (failed and isinstance(item.get('failure'), (dict, str)) and bool(item['failure'])),
            'Desktop image generation has no explicit successful or failed terminal event')
    start, end = payload.get('started_at_ms'), payload.get('completed_at_ms')
    require(type(start) is int and type(end) is int and 0 < start <= end,
            'Missing or invalid native desktop lifecycle times')
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        started = epoch + timedelta(milliseconds=start)
        completed = epoch + timedelta(milliseconds=end)
    except OverflowError as exc:
        raise ValueError('Invalid native desktop lifecycle times') from exc
    require(started >= timestamp(request.get('prepared_at')), 'Desktop call precedes production request')
    require(started + timedelta(milliseconds=1) > timestamp(intent['recorded_at']),
            'Native call must follow its standard dispatch intent')
    if invocation_row is not None:
        require(timestamp(intent['recorded_at']) <= timestamp(invocation_row.get('timestamp')) < completed + timedelta(milliseconds=1),
                'Native invocation must follow its standard dispatch intent')
    require(completed <= timestamp(row.get('timestamp')) <= datetime.now(timezone.utc),
            'Invalid or future desktop completion timestamp')
    # The envelope only points to evidence. Author-supplied times/state cannot
    # replace the original host fields, including when copied into an envelope.
    require('occurred_at' not in binding and 'started_at' not in binding and 'previous' not in binding,
            'Desktop lifecycle times must come from native rollout evidence')
    if failed:
        require(not item.get('savedPath') and not item.get('result') and binding.get('outputs', []) == [],
                'Failed desktop terminal cannot claim saved outputs')
        return dict(binding, state='failed', outputs=[], failure=item['failure'],
                    started_at=started.isoformat(), occurred_at=completed.isoformat(),
                    host_thread_id=payload['thread_id'], host_turn_id=payload['turn_id'])
    saved = item.get('savedPath')
    require(isinstance(saved, str) and bool(saved.strip())
            and (PureWindowsPath(saved).is_absolute() or PurePosixPath(saved).is_absolute()),
            'Missing native desktop saved output path')
    require(PureWindowsPath(saved).name == call_id + '.png', 'Desktop saved path differs from call ID')
    require(isinstance(item.get('result'), str) and bool(item['result']), 'Missing native desktop image payload')
    try:
        raw = base64.b64decode(item['result'], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('Invalid native desktop image payload') from exc
    image_hash = hashlib.sha256(raw).hexdigest()
    outputs = binding.get('outputs')
    require(isinstance(outputs, list) and len(outputs) == 1
            and {r.get('path') for r in outputs} == set(request.get('output_files', [])),
            'Desktop saved outputs differ from request')
    require(digest(bound_file(root, outputs[0])) == image_hash,
            'Desktop output bytes differ from native image payload')
    return dict(binding, state='saved', started_at=started.isoformat(), occurred_at=completed.isoformat(),
                host_saved_path=saved, host_thread_id=payload['thread_id'], host_turn_id=payload['turn_id'])
