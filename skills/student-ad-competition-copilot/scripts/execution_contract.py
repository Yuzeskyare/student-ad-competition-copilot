"""Dispatch-time bindings and observable lifecycle; not a filesystem sandbox."""
from datetime import datetime, timezone
from pathlib import Path
import math
import ast
import tokenize

PROFILE = 'bound-production-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def dispatch_inputs(root, manifest, contract, request):
    from review_contract import bound_file, inside, load, digest
    if manifest.get('direction_contract') == 'print-direction-v6':
        from validate_print_ad_run import validate_direction_blind_review, validate_main_visual_dispatch_v6
        direction = validate_direction_blind_review(root, manifest)
        require(direction['passed'], 'Direction choice must be completed before production: ' + str(direction['evidence']))
        validate_main_visual_dispatch_v6(root, manifest, request)
    require(request.get('execution_profile') == PROFILE,
            'New dispatch requires bound-production-v1; preserve legacy requests and create a bound successor')
    require('input_files' in request and isinstance(request['input_files'], list), 'Declare actual input_files')
    inputs = {bound_file(root, ref) for ref in request['input_files']}
    require(inputs or bool(request.get('no_file_inputs_reason')), 'Empty inputs need an applicable reason')
    mode = request.get('brand_asset_mode')
    require(mode in {'restricted', 'not-used'}, 'Declare restricted or not-used brand assets')
    if mode == 'restricted':
        require(isinstance(request.get('asset_scope'), dict), 'Restricted assets require bound asset_scope')
        require(bool(request['asset_scope'].get('used_origins')), 'Restricted production needs actual used origins')
        inputs |= {bound_file(root, ref) for key in ('allowed_assets', 'used_origins')
                   for ref in request['asset_scope'].get(key, [])}
    else:
        require(bool(request.get('brand_asset_reason')), 'Explain why no brand assets are used')
        require(not request.get('asset_scope', {}).get('used_origins'), 'not-used cannot declare used brand assets')
    command = request.get('command')
    if request.get('operation') == 'local' or command is not None:
        require(isinstance(command, list) and command, 'Local production needs a command array')
        # Bind file arguments (including interpreter-invoked scripts); executable
        # runtimes are not artwork inputs. Inline code is bound by request hash.
        skip_inline = False
        for arg in command[1:]:
            require(isinstance(arg, str), 'Command arguments must be strings')
            if skip_inline:
                skip_inline = False
                continue
            if arg.lower() in {'-c', '-command', '-encodedcommand'}:
                skip_inline = True
                continue
            if arg.startswith('-'):
                continue
            candidate = Path(arg)
            candidate = candidate.resolve() if candidate.is_absolute() else (root/candidate).resolve()
            if candidate.is_file():
                require(candidate in inputs, 'Command file argument is not a bound input: '+arg)
                if candidate.suffix.lower() == '.py':
                    try:
                        with tokenize.open(candidate) as source:
                            ast.parse(source.read(), filename=str(candidate))
                    except (SyntaxError, UnicodeError) as exc:
                        raise ValueError('Python input syntax error before dispatch: '+str(exc)) from exc
    outputs = request.get('output_files')
    require(isinstance(outputs, list) and outputs, 'Declare concrete output_files before dispatch')
    paths = [inside(root, p) for p in outputs]
    require(len(set(paths)) == len(paths), 'Duplicate output paths')
    protected = inputs | {bound_file(root, r) for r in contract['final_artifacts']}
    for path in paths:
        require(path not in protected and not path.exists(), 'Production must not overwrite inputs or existing outputs')
    control_path = inside(root, manifest.get('execution_control'))
    control = load(control_path)
    require(control.get('run_id') == manifest['run_id'], 'Execution control run mismatch')
    require(control.get('state') == 'active', 'Execution is stopped or unresolved; no new work may dispatch')
    require(control.get('monitoring') in {'not-requested', 'active', 'revoked'}, 'Declare actual monitoring state')
    if control['monitoring'] == 'active':
        signal = load(bound_file(root, control.get('latest_signal')))
        require(control.get('monitor_kind') in {'usage-reset', 'user-condition'}, 'Declare the actual signal policy')
        if control['monitor_kind'] == 'usage-reset':
            baseline = load(bound_file(root, signal.get('baseline')))
            reading = load(bound_file(root, signal.get('reading')))
            confirmation = load(bound_file(root, signal['confirmation'])) if signal.get('confirmation') else None
            require(evaluate_usage_signal(baseline, reading, confirmation)['decision'] == 'continue',
                    'Actual usage signal requires confirmation or stop; declared continue cannot override it')
        require(signal.get('decision') == 'continue', 'Stop/unknown signal requires resolution before dispatch')
        require(bool(signal.get('basis')), 'Signal decision needs its actual basis')
    return dict(path=control_path.relative_to(root).as_posix(), sha256=digest(control_path))


def evaluate_usage_signal(baseline, reading, confirmation=None):
    """Only for a user-requested reset stop policy; performs no account query."""
    identity = ('account_id', 'limit_id', 'window_minutes')
    def valid(value):
        return (isinstance(value, dict) and all(value.get(k) is not None for k in identity)
                and type(value.get('used_percent')) in {int, float} and 0 <= value['used_percent'] <= 100
                and type(value.get('resets_at')) in {int, float} and math.isfinite(value['resets_at']))
    if not valid(baseline) or not valid(reading) or any(baseline[k] != reading[k] for k in identity):
        return dict(decision='unknown', basis='Missing or different account/window evidence')
    drop = reading['used_percent'] < baseline['used_percent']
    advanced = reading['resets_at'] > baseline['resets_at']
    if reading['resets_at'] < baseline['resets_at']:
        return dict(decision='unknown', basis='Reset time moved backwards; do not infer continuation')
    if not drop and not advanced:
        return dict(decision='continue', basis='No reset signal in the comparable readings')
    if not (drop and advanced) or not valid(confirmation):
        return dict(decision='unknown', basis='Signal requires minimal independent confirmation')
    if (any(confirmation[k] != baseline[k] for k in identity)
            or confirmation['used_percent'] >= baseline['used_percent']
            or confirmation['resets_at'] <= baseline['resets_at']):
        return dict(decision='unknown', basis='Confirmation is not comparable or does not confirm reset')
    return dict(decision='stop', basis='Same account/window drop and advanced reset confirmed')


def validate_events(root, contract, pending=None):
    from review_contract import bound_file, load, timestamp
    requests = {r['sha256']: load(bound_file(root, r)) for r in contract['production_requests']}
    previous = {}
    transitions = {None: {'started'}, 'started': {'running', 'returned', 'failed'},
                   'running': {'running', 'returned', 'failed'}, 'returned': {'saved'}}
    events = [(ref, load(bound_file(root, ref))) for ref in contract.get('production_events', [])]
    if pending is not None:
        events.append(pending)  # Validated in memory before an append helper writes a new snapshot.
    for ref, event in events:
        key = event.get('request_sha256')
        require(key in requests and event.get('request_id') == requests[key]['id'], 'Lifecycle request mismatch')
        require(isinstance(event.get('call_id'), str) and event['call_id'].strip(), 'Use actual host call ID')
        at = timestamp(event.get('occurred_at'))
        require(at <= datetime.now(timezone.utc), 'Future lifecycle event')
        evidence = load(bound_file(root, event.get('evidence')))
        require(evidence.get('call_id') == event['call_id'] and evidence.get('state') == event.get('state'),
                'Lifecycle state must match bound host evidence')
        require(timestamp(evidence.get('occurred_at')) == at, 'Lifecycle time differs from host evidence')
        prior = previous.get(key)
        state = prior[0]['state'] if prior else None
        require(event.get('state') in transitions.get(state, set()), 'Invalid lifecycle transition or duplicate start')
        if prior:
            require(event.get('previous') == prior[1] and event['call_id'] == prior[0]['call_id'], 'Broken lifecycle chain')
            require(at >= timestamp(prior[0]['occurred_at']), 'Lifecycle time moved backwards')
        else:
            require(event.get('previous') is None, 'First event cannot inherit an unknown event')
        if event['state'] == 'saved':
            require(bool(event.get('outputs')), 'Saved requires actual output files')
            require(event['outputs'] == evidence.get('outputs'), 'Saved outputs differ from host evidence')
            expected = set(requests[key].get('output_files', []))
            require({r['path'] for r in event['outputs']} == expected, 'Saved outputs differ from request')
            for output in event['outputs']:
                bound_file(root, output)
        previous[key] = (event, ref)
    return {key: value[0] for key, value in previous.items()}


def normalize_event(source, *, time_value, time_unit, time_basis):
    """Convert known time units only. Missing IDs/time never become approvals."""
    require(time_basis in {'message', 'turn', 'review-event'}, 'Unsupported time basis')
    require(time_unit in {'seconds', 'milliseconds', 'iso'}, 'Declare original time unit')
    if time_unit == 'iso':
        from review_contract import timestamp
        at = timestamp(time_value)
    else:
        require(type(time_value) in {int, float}, 'Unix time must be numeric')
        at = datetime.fromtimestamp(time_value/(1000 if time_unit == 'milliseconds' else 1), timezone.utc)
    result = dict(source)
    result.update(occurred_at=at.isoformat(), time_basis=time_basis,
                  original_time=dict(value=time_value, unit=time_unit), original_event=dict(source))
    # human_source still checks actual IDs, text and matching turn/message basis.
    return result
