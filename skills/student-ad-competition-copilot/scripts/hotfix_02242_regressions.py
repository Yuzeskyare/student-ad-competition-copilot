"""Explicitly SYNTHETIC native-event fixtures, zero generation/model calls."""
import base64
import copy
import json
from datetime import datetime, timezone, timedelta


def run(root, save, text, stages, cli=None, legacy=False):
    from PIL import Image
    from review_contract import digest
    from validate_submission import source_resolution_report
    from execution_contract import validate_events

    def ref(name):
        return dict(path=name, sha256=digest(root/name))

    def case(label, action, expected=True):
        try:
            result = action()
            accepted = True
            error = None
        except (ValueError, KeyError, TypeError, OSError) as exc:
            result = None
            accepted = False
            error = str(exc)
        stages.append(dict(stage='02242-'+label, expected_accept=expected, actual_accept=accepted, error=error, result=result))
        assert accepted == expected, (label, error, result)
        return result

    (root/'02242').mkdir(exist_ok=True)
    Image.new('RGB', (1055, 1491), 'white').save(root/'02242/source.png')
    Image.new('RGB', (1404, 1985), 'white').save(root/'02242/export.png', dpi=(120,120))
    layer = dict(path='source.png', kind='raster', placed_mm=[223.3083333333, 315.595], minimum_ppi=120,
                 requirement_basis='SYNTHETIC reproduction of the real 120ppi task requirement')

    def resolution(label, placed, expected):
        src = save('02242/'+label+'.json', dict(layers=[dict(layer, placed_mm=placed)]))
        report = source_resolution_report(root/src['path'], Image)
        actual = report[0]['meets_requirement']
        stages.append(dict(stage='02242-'+label, expected_accept=expected, actual_accept=actual, report=report))
        assert actual == expected, (label, report)
        if cli:
            cli('02242-'+label+'-native-file-check', 'validate_submission.py',
                ['--competition','academy-award','--input-dir',root/'02242','--include','export.png',
                 '--aigc-used','no','--source-manifest',root/src['path'],'--output',root/'02242'/('technical-'+label+'.json')],
                accepted_codes=(0,) if expected else (1,))
        return report

    resolution('exact-120', layer['placed_mm'], not legacy)
    resolution('below-120', [223.3083333333, 1491*25.4/119.99], False)
    resolution('tiny-below-120', [223.3083333333, 315.595000000001], False)
    resolution('above-120', [223.3083333333, 315.594999999999], True)

    now = datetime.now(timezone.utc)
    start = int((now-timedelta(seconds=4)).timestamp()*1000)
    end = start+1000
    request = dict(id='SYNTHETIC-desktop-generation', operation='external', execution_profile='bound-production-v1',
                   prepared_at=(now-timedelta(seconds=10)).isoformat(), output_files=['02242/source.png'])
    request_ref = save('02242/request.json', request)
    call_id = 'exec-SYNTHETIC-desktop-generation'
    meta = dict(type='session_meta', payload=dict(id='SYNTHETIC-desktop-session', originator='Codex Desktop', source='vscode'))
    native = dict(type='event_msg', timestamp=now.isoformat(), payload=dict(type='item_completed',
                  thread_id=meta['payload']['id'], turn_id='SYNTHETIC-desktop-turn', started_at_ms=start, completed_at_ms=end,
                  item=dict(type='Extension', kind='image_gen.generation', id=call_id, status='completed',
                            failure=None, savedPath='C:\\SYNTHETIC-generated-images\\'+call_id+'.png',
                            result=base64.b64encode((root/'02242/source.png').read_bytes()).decode('ascii'))))

    def binding(label, raw=None, header=None, edit=None, duplicate=False):
        rows=[header or meta, raw or native]
        if duplicate:
            rows.append(rows[-1])
        evidence=text('02242/'+label+'.jsonl', ''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
        event=dict(profile='codex-desktop-imagegen-v1', request_id=request['id'], request_sha256=request_ref['sha256'],
                   call_id=call_id, evidence=evidence, outputs=[ref('02242/source.png')])
        if edit:
            edit(event)
        event_ref=save('02242/'+label+'-binding.json', event)
        return dict(production_requests=[request_ref], production_events=[event_ref])

    good=binding('native-completed')
    result=case('native-completed-with-host-times-and-bytes', lambda:validate_events(root,good), not legacy)
    if result:
        result=result[request_ref['sha256']]
        assert result['state']=='saved' and result['started_at'] < result['occurred_at']
    mutations=[
        ('missing-native-call-id', lambda r:r['payload']['item'].pop('id')),
        ('wrong-native-call-id', lambda r:r['payload']['item'].update(id='exec-OTHER')),
        ('wrong-output-payload', lambda r:r['payload']['item'].update(result=base64.b64encode(b'SYNTHETIC wrong output').decode('ascii'))),
        ('wrong-saved-output-path', lambda r:r['payload']['item'].update(savedPath='C:\\SYNTHETIC-generated-images\\OTHER.png')),
        ('missing-start-time', lambda r:r['payload'].pop('started_at_ms')),
        ('missing-completion-time', lambda r:r['payload'].pop('completed_at_ms')),
        ('backwards-times', lambda r:r['payload'].update(completed_at_ms=start-1)),
        ('failed-native-call', lambda r:r['payload']['item'].update(status='failed',failure='SYNTHETIC failure')),
        ('wrong-event-kind', lambda r:r['payload']['item'].update(kind='web.search')),
        ('wrong-thread', lambda r:r['payload'].update(thread_id='SYNTHETIC-other-thread')),
    ]
    for label, mutate in mutations:
        raw=copy.deepcopy(native)
        mutate(raw)
        contract=binding(label,raw)
        case(label,lambda c=contract:validate_events(root,c),False)
    for label, edit in [
        ('missing-binding-call-id', lambda e:e.pop('call_id')),
        ('author-filled-times', lambda e:e.update(occurred_at=now.isoformat(),started_at=(now-timedelta(seconds=1)).isoformat())),
        ('wrong-output-reference', lambda e:e.update(outputs=[ref('02242/export.png')])),
        ('wrong-output-hash', lambda e:e['outputs'][0].update(sha256='0'*64)),
    ]:
        contract=binding(label,edit=edit)
        case(label,lambda c=contract:validate_events(root,c),False)
    for label, contract in [
        ('duplicate-native-event', binding('duplicate-native-event',duplicate=True)),
        ('author-chain-without-native-event', binding('author-chain', dict(call_id=call_id,state='saved',occurred_at=now.isoformat()))),
        ('wrong-host-metadata', binding('wrong-host-metadata',header=dict(type='session_meta',payload=dict(id='SYNTHETIC-desktop-session',originator='author',source='vscode')))),
    ]:
        case(label,lambda c=contract:validate_events(root,c),False)
    stages.append(dict(stage='02242-all-regressions-complete', passed=True, image_generation_calls=0))
