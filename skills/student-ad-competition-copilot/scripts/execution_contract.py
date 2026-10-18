"""Dispatch-time bindings and observable lifecycle; not a filesystem sandbox."""
from datetime import datetime, timezone
from pathlib import Path
import math
import ast
import tokenize

PROFILE = 'bound-production-v1'


def package_checker_hashes():
    """Bind the distributed scripts, not author-supplied paths or hashes."""
    from review_contract import digest, load
    base = Path(__file__).resolve().parent
    files = {r['path']: r['sha256'] for r in load(base.parent/'version.json')['files']}
    result = {}
    for path in sorted(base.glob('*.py')):
        key = 'scripts/'+path.name
        value = digest(path)
        require(files.get(key) == value, 'Checker differs from this Skill package manifest: '+key)
        result[key] = value
    return result


def guard_runtime_identity():
    """Reject imported guard wrappers and changed in-memory checker functions."""
    import sys, types
    base = Path(__file__).resolve().parent
    entry = Path(getattr(sys.modules.get('__main__'), '__file__', '')).resolve()
    require(entry == base/'guard_production.py', 'Run package guard_production.py directly; wrappers/monkeypatches are forbidden')
    hashes = package_checker_hashes()
    def code_value(code):
        return (code.co_code, code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars,
                code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount, code.co_flags,
                tuple(code_value(v) if isinstance(v, types.CodeType) else v for v in code.co_consts))
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename or Path(filename).resolve().parent != base:
            continue
        path = Path(filename).resolve()
        if path.suffix != '.py':
            continue
        compiled = compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
        codes = {c.co_name: c for c in compiled.co_consts if isinstance(c, types.CodeType)}
        for name, expected in codes.items():
            actual = getattr(module, name, None)
            if isinstance(actual, types.FunctionType):
                require(code_value(actual.__code__) == code_value(expected),
                        'In-memory checker was replaced: '+path.name+':'+name)
    return dict(profile='package-guard-v1', entrypoint='scripts/guard_production.py', checker_sha256=hashes)


def verify_artwork_release(root, manifest, artifact_ref, receipt_ref=None):
    """A preflight-only or foreign-checker receipt cannot release complete artwork."""
    from review_contract import bound_file, read_contract, load, fingerprint
    artifact_path = bound_file(root, artifact_ref)
    contract, rows = read_contract(root, manifest)
    receipts = [load(bound_file(root, receipt_ref))] if receipt_ref else [load(bound_file(root, r)) for r in contract.get('production_receipts', [])]
    expected = package_checker_hashes()
    requests = {r['sha256']: load(bound_file(root, r)) for r in contract['production_requests']}
    for receipt in receipts:
        request = requests.get(receipt.get('request_sha256'))
        if not request or receipt.get('request_id') != request.get('id') or receipt.get('request') != request:
            continue
        provenance = receipt.get('guard_identity', {})
        if (receipt.get('run_id') != manifest['run_id'] or receipt.get('status') != 'authorized'
            or receipt.get('dispatch_checked') is not True or receipt.get('production_state') != 'completed'
            or receipt.get('executed') is not True or receipt.get('command_returncode') != 0):
            continue
        from package_upgrade_contract import validate_historical_guard
        request_ref=next(r for r in contract['production_requests'] if r['sha256']==receipt['request_sha256'])
        if provenance == dict(profile='package-guard-v1',entrypoint='scripts/guard_production.py',checker_sha256=expected):
            from package_upgrade_contract import guard_source
            source=guard_source(root,manifest,receipt)
        else:
            source=validate_historical_guard(root,manifest,receipt,request,request_ref,rows)
        outputs=receipt.get('outputs', [])
        if {r.get('path') for r in outputs} != set(request.get('output_files', [])):
            continue
        for output in outputs:
            bound_file(root, output)
        if any(bound_file(root, r)==artifact_path and r['sha256']==artifact_ref['sha256'] for r in outputs):
            return dict(request_id=receipt['request_id'], request_sha256=receipt['request_sha256'],
                         artifact_sha256=artifact_ref['sha256'], guard_identity=provenance, source_package=source)
    raise ValueError('Complete artwork has no valid package guard release: missing receipt, changed output or foreign/wrapped checker. Stop and report; do not bypass or backfill history.')


def release_required(root, manifest):
    """Only consumption of complete artwork under print gate 0.17+ needs release."""
    if manifest.get('category') != 'print-ad':
        return False
    from review_contract import inside, load
    path = manifest.get('artifacts', {}).get('quality_gate_results')
    if not path:
        return manifest.get('product_contract') == 'print-product-v3'
    gate = load(inside(root,path)).get('definition_set_id','')
    try:
        return gate.startswith('print-ad.') and tuple(int(x) for x in gate[9:].split('.')) >= (0,17,0)
    except ValueError:
        raise ValueError('Unknown print quality gate; do not infer a legacy exemption')


def verify_complete_artworks(root, manifest, contract=None):
    if not release_required(root,manifest):
        return []
    from review_contract import read_contract
    if contract is None: contract, _ = read_contract(root, manifest)
    refs=list(contract.get('final_artifacts', []))
    for row in manifest.get('core_creative_review', {}).get('assessments', []):
        refs.extend([row['artifact'], row['observed_image']])
    return [verify_artwork_release(root,manifest,r) for r in refs]


def require(value, message):
    if not value:
        raise ValueError(message)


def dispatch_inputs(root, manifest, contract, request):
    from review_contract import bound_file, inside, load, digest
    if manifest.get('direction_contract') in {'print-direction-v6','print-direction-v7','print-direction-v8','print-direction-v9','print-direction-v10','print-direction-v11','print-direction-v12'}:
        from validate_print_ad_run import validate_direction_blind_review, validate_main_visual_dispatch_v6
        direction = validate_direction_blind_review(root, manifest)
        require(direction['passed'], 'Direction choice must be completed before production: ' + str(direction['evidence']))
        validate_main_visual_dispatch_v6(root, manifest, request)
    if manifest.get('direction_contract')=='print-direction-v7' or manifest.get('product_contract')=='print-product-v2':
        require(manifest.get('direction_contract')=='print-direction-v7' and manifest.get('product_contract')=='print-product-v2','New dispatch cannot downgrade causal/product contracts')
        gate=load(inside(root,manifest['artifacts']['quality_gate_results']))
        require(gate.get('definition_set_id')=='print-ad.0.16.0','New dispatch requires print-ad.0.16.0')
        from visual_review_contract import validate_product_dispatch_v2
        validate_product_dispatch_v2(root,manifest,request)
    if manifest.get('direction_contract') in {'print-direction-v8','print-direction-v9','print-direction-v10','print-direction-v11','print-direction-v12'} or manifest.get('product_contract')=='print-product-v3':
        require(manifest.get('direction_contract') in {'print-direction-v8','print-direction-v9','print-direction-v10','print-direction-v11','print-direction-v12'} and manifest.get('product_contract')=='print-product-v3', 'Current direction/product contracts cannot be downgraded')
        require(load(inside(root,manifest['artifacts']['quality_gate_results'])).get('definition_set_id') in {'print-ad.0.17.0','print-ad.0.18.0','print-ad.0.19.0','print-ad.0.20.0','print-ad.0.21.0','print-ad.0.22.0'},'Current dispatch requires print-ad.0.17.0 or later current contract')
        from visual_review_contract import validate_product_dispatch_v2
        validate_product_dispatch_v2(root,manifest,request)
        from validate_print_ad_run import validate_repeated_failure_handoff
        validate_repeated_failure_handoff(root,manifest,for_dispatch=True)
    from visual_review_contract import validate_brand_placement_plan
    if manifest.get('core_review_contract') in {'print-core-product-v4','print-core-product-v5','print-core-product-v6','print-core-product-v7','print-core-product-v8'}:
        validate_brand_placement_plan(root,manifest,request)
    # Re-evaluate historical bindings before dispatch, without executing old commands.
    if manifest.get('package_upgrades') or release_required(root,manifest):
        verify_complete_artworks(root,manifest,contract)
        from package_upgrade_contract import validate_historical_guard
        from review_contract import decisions
        rows=decisions(root,contract)
        requests={r['sha256']:(r,load(bound_file(root,r))) for r in contract['production_requests']}
        for ref in contract.get('production_receipts',[]):
            receipt=load(bound_file(root,ref))
            require(receipt.get('request_sha256') in requests, 'Historical receipt refers to an unregistered production request')
            request_ref,original=requests[receipt['request_sha256']]
            validate_historical_guard(root,manifest,receipt,original,request_ref,rows)
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
        if event.get('profile') == 'codex-desktop-imagegen-v1':
            require(key not in previous, 'Duplicate or mixed desktop lifecycle evidence')
            from desktop_host_evidence import completed_image_event
            previous[key] = (completed_image_event(root, event, requests[key]), ref)
            continue
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


def validate_new_run_gate(root, manifest, contract, rows):
    """Historical continuation uses bound original human evidence, not a chosen version."""
    from review_contract import human_source, timestamp, load, inside
    cutoff = timestamp('2026-10-11T07:00:00Z')
    origins = [human_source(root,r['source'],r['quote']) for r in rows.values()]
    historical = bool(origins) and min(origins) < cutoff
    gate_path=manifest.get('artifacts',{}).get('quality_gate_results')
    gate = load(inside(root,gate_path))['definition_set_id'] if gate_path else None
    current_cutoff=timestamp('2026-10-11T08:57:54Z')
    current_historical=bool(origins) and min(origins)<current_cutoff
    latest_cutoff=timestamp('2026-10-11T10:54:26.721687+00:00')
    latest_historical=bool(origins) and min(origins)<latest_cutoff
    latest=(gate=='print-ad.0.20.0' and manifest.get('product_contract')=='print-product-v3' and manifest.get('direction_contract')=='print-direction-v10' and manifest.get('core_review_contract')=='print-core-product-v6')
    previous=(gate=='print-ad.0.19.0' and manifest.get('product_contract')=='print-product-v3' and manifest.get('direction_contract')=='print-direction-v9' and manifest.get('core_review_contract')=='print-core-product-v5')
    scene_cutoff=timestamp('2026-10-11T11:36:31.792517+00:00')
    scene_historical=bool(origins) and min(origins)<scene_cutoff
    scene_current=(gate=='print-ad.0.21.0' and manifest.get('product_contract')=='print-product-v3' and manifest.get('direction_contract')=='print-direction-v10' and manifest.get('core_review_contract')=='print-core-product-v7')
    artwork_cutoff=timestamp('2026-10-11T22:54:07.571875+00:00')
    artwork_historical=bool(origins) and min(origins)<artwork_cutoff
    artwork_current=(gate=='print-ad.0.22.0' and manifest.get('product_contract')=='print-product-v3' and manifest.get('direction_contract') in {'print-direction-v11','print-direction-v12'} and manifest.get('core_review_contract')=='print-core-product-v8')
    if not artwork_historical:
        require(artwork_current,'New print run must use the current product meaning and complete-artwork contracts; historical continuation needs bound original human evidence before the cutover.')
    elif not scene_historical:
        require(artwork_current or scene_current,'New print run must use the current product meaning and visible scene evidence gate; historical continuation needs bound original human evidence before the cutover.')
    elif not latest_historical:
        require(artwork_current or scene_current or latest,'New print run must use the current product meaning gate and contracts; historical continuation needs bound original human evidence before the cutover.')
    elif not current_historical:
        require(artwork_current or scene_current or latest or previous,'New print run must use the contract active at its bound original event; no downgrade')
    elif not historical:
        require(artwork_current or scene_current or latest or previous or (gate=='print-ad.0.18.0' and manifest.get('direction_contract')=='print-direction-v8' and manifest.get('core_review_contract')=='print-core-product-v4'),'New print run must use the contract active at its bound original event; no downgrade')
    provenance_historical = bool(origins) and min(origins) < timestamp('2026-10-12T09:18:51.043861+00:00')
    require(provenance_historical or manifest.get('direction_provenance_contract') == 'print-direction-provenance-v1', 'New print run must use print-direction-provenance-v1; historical continuation needs bound original human evidence before the cutover.')
    return dict(historical_continuation=historical, gate=gate)
