"""Read native Desktop rollout completion evidence; never invent a time chain."""
import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import PureWindowsPath, PurePosixPath


def completed_image_event(root, binding, request):
    from review_contract import bound_file, digest, timestamp
    from execution_contract import require

    require(request.get('operation') == 'external', 'Desktop evidence needs an external request')
    call_id = binding['call_id']
    rollout = bound_file(root, binding.get('evidence'))
    meta = None
    matches = []
    with rollout.open(encoding='utf-8-sig') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('type') == 'session_meta':
                require(meta is None, 'Duplicate desktop session metadata')
                meta = row.get('payload', {})
            payload = row.get('payload', {})
            item = payload.get('item', {})
            if (row.get('type') == 'event_msg' and payload.get('type') == 'item_completed'
                    and item.get('type') == 'Extension' and item.get('kind') == 'image_gen.generation'
                    and item.get('id') == call_id):
                matches.append((row, payload, item))
    require(meta is not None and meta.get('originator') == 'Codex Desktop' and meta.get('source') == 'vscode',
            'Missing native Codex Desktop session metadata')
    require(len(matches) == 1, 'Desktop image call ID must identify one native completion event')
    row, payload, item = matches[0]
    require(bool(meta.get('id')) and payload.get('thread_id') == meta['id']
            and isinstance(payload.get('turn_id'), str) and bool(payload['turn_id'].strip()),
            'Desktop event must bind its session and turn')
    require(item.get('status') == 'completed' and item.get('failure') is None,
            'Desktop image generation did not complete successfully')
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
    require(completed <= timestamp(row.get('timestamp')) <= datetime.now(timezone.utc),
            'Invalid or future desktop completion timestamp')
    # The envelope only points to evidence. Author-supplied times/state cannot
    # replace the original host fields, including when copied into an envelope.
    require('occurred_at' not in binding and 'started_at' not in binding and 'previous' not in binding,
            'Desktop lifecycle times must come from native rollout evidence')
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
