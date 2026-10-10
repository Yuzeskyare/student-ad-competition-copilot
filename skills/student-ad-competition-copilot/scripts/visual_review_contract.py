"""Validate final-pixel evidence relationships, not visual taste or human identity."""
from datetime import datetime, timezone
import math

from review_contract import artifact, bound_file, cancelled_requests, coverage, inside, latest, load, read_contract, timestamp

BASE_CHECKS = {'composition', 'occlusion', 'text-legibility', 'residue', 'frontstage-role',
               'source-visibility', 'crop-safety', 'positive-art-direction'}
PRODUCT_CHECKS = {'perspective', 'light-material', 'contact-shadow', 'occlusion', 'mechanism-role', 'official-label-fidelity'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def box(value):
    require(isinstance(value, list) and len(value) == 4 and
            all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in value),
            'Bounds must be four finite numbers [left, top, right, bottom]')
    require(value[2] > value[0] and value[3] > value[1], 'Bounds must have positive area')
    return value


def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def image_file(root, ref):
    from PIL import Image
    path = bound_file(root, ref)
    with Image.open(path) as image:
        require(image.format in {'PNG', 'JPEG'}, 'Visual evidence must be a PNG or JPEG render')
        image.load()
        return image.convert('RGB')


def observations(rows, required, view_ids, pending=None):
    require(isinstance(rows, list), 'Visual observations must be a list')
    mapped = {}
    for row in rows:
        key = row['check']
        require(key not in mapped, 'Duplicate visual check')
        state = row.get('status')
        require(state in {'pass', 'not-applicable', 'pending', 'not-run', 'fail'} and nonempty(row.get('observation')),
                'Visual checks need a known status and a concrete observation or pending reason')
        require(state != 'fail', 'Observed visual failure: '+str(key))
        if key in {'composition', 'positive-art-direction', 'frontstage-role', 'orientation-comparison',
                   'visual-only-meaning', 'three-second-recall', 'communication-clarity', 'visible-element-delete-test'}:
            require(state != 'not-applicable', 'Core communication/design checks cannot be marked not-applicable')
        require(isinstance(row.get('views'), list) and row['views'] and set(row['views']) <= view_ids,
                'Observation must cite current pixel views')
        mapped[key] = row
        if state in {'pending', 'not-run'}:
            require(pending is not None, 'Visual check is unfinished: '+str(key))
            pending.append({'check': key, 'kind': 'human' if key in {'three-second-recall', 'communication-clarity', 'visual-only-meaning', 'visible-element-delete-test'} else 'work',
                            'reason': row['observation']})
    require(required <= set(mapped), 'Missing applicable final-pixel observations: '+str(sorted(required-set(mapped))))
    return mapped


def inspect_unit(root, unit, rows, track, proportional=False, pending=None, qualitative=False):
    from PIL import Image, ImageChops
    target = unit['artifact']
    keys = artifact(root, target)
    require(len(keys) == 1, 'One visual evidence record must identify exactly one artwork/page')
    record = load(bound_file(root, unit['render_record']))
    require(artifact(root, record['source']) == keys, 'Render source differs from the reviewed final artifact/version/unit')
    require(nonempty(record.get('renderer')) and record.get('target_renderer_verified') is True,
            'Target-renderer verification is missing; font-family checks do not prove glyph rendering')
    require(timestamp(record['created_at']) <= datetime.now(timezone.utc), 'Render timestamp is in the future')
    bound_file(root, record['execution_evidence'])
    views = record['views']
    require(isinstance(views, list), 'Rendered views must be a list')
    by_scale = {}; by_id = {}; images = {}
    for view in views:
        require(nonempty(view.get('id')) and view['id'] not in by_id, 'View IDs must be unique')
        require(view.get('scale') in {'thumbnail', 'native', 'detail'}, 'Unknown viewing scale')
        by_scale.setdefault(view['scale'], []).append(view)
        by_id[view['id']] = view
        images[view['id']] = image_file(root, view['file'])
    require(({'native'} <= set(by_scale) if proportional else set(by_scale) == {'thumbnail', 'native', 'detail'}) and len(by_scale['native']) == 1,
            'Each artwork/page needs thumbnail, one native render and detail crops')
    native_view = by_scale['native'][0]; native = images[native_view['id']]
    for view in by_scale.get('thumbnail', []):
        thumb = images[view['id']]
        require(thumb.width < native.width and thumb.height < native.height, 'Thumbnail must declare a smaller actual viewing scale')
        expected = native.copy(); expected.thumbnail(thumb.size, Image.Resampling.LANCZOS)
        require(expected.size == thumb.size and ImageChops.difference(expected, thumb).getbbox() is None,
                'Thumbnail pixels are not derived from the current native render')
    for view in by_scale.get('detail', []):
        bounds = box(view['native_bounds'])
        require(contains([0, 0, native.width, native.height], bounds), 'Detail crop falls outside the native render')
        require(isinstance(view.get('zoom'), (int, float)) and 1.5 <= view['zoom'] <= 4,
                'Detail view must record a readable enlargement (normally 150–200%)')
        require(view.get('native_sha256') == native_view['file']['sha256'], 'Detail crop is linked to an old render')
        require(all(isinstance(n, int) for n in bounds), 'Native crop coordinates must use whole pixels')
        expected = native.crop(bounds)
        expected = expected.resize((round(expected.width*view['zoom']), round(expected.height*view['zoom'])), Image.Resampling.LANCZOS)
        actual = images[view['id']]
        require(expected.size == actual.size and ImageChops.difference(expected, actual).getbbox() is None,
                'Detail pixels are not derived from the declared current native region')
    communication = 'communication-clarity' if qualitative else 'three-second-recall'
    required = BASE_CHECKS | ({'visual-only-meaning', communication, 'visible-element-delete-test'} if track == 'print-ad' else {'orientation-comparison'})
    checked = observations(expand_checks(unit['checks']) if proportional else unit['checks'], required, set(by_id), pending)
    if qualitative:
        require('three-second-recall' not in checked, 'Use communication-clarity; timed tests belong in optional audience_tests')
        if track == 'print-ad':
            judgment = checked[communication]
            if judgment['status'] == 'pass':
                method = judgment.get('assessment_method')
                require(method in {'author-inspection', 'user-acceptance'}, 'Declare the actual qualitative assessment method')
                if method == 'user-acceptance':
                    decision = rows.get(judgment.get('human_decision'))
                    current = latest([r for r in rows.values() if r['stage'] in {'representative', 'final'}
                                      and keys <= coverage(root, r['reviewed_artifacts'])])
                    require(decision is not None and decision == current and decision['decision'] == 'pass'
                            and keys <= coverage(root, decision['reviewed_artifacts']),
                            'User acceptance must cite an actual decision for this version and scope')
        inspect_audience_tests(root, unit, keys)
    if proportional:
        inspect_proportional(root, unit, by_id, pending)
        return keys
    inventory = unit['visible_elements']
    require(isinstance(inventory, list), 'Visible-element inventory is required, including raster text')
    ids = [item['id'] for item in inventory]
    require(len(ids) == len(set(ids)), 'Visible element IDs must be unique')
    label_ids = {item['id'] for item in inventory if item.get('kind') == 'embedded-label'}
    product_ids = {item['id'] for item in inventory if item.get('kind') == 'product'}
    text_ids = {item['id'] for item in inventory if item.get('kind') in {'text', 'embedded-label'}}
    for item in inventory:
        require(item.get('kind') in {'text', 'embedded-label', 'product', 'other'} and nonempty(item.get('role')),
                'Each visible element needs a kind and an audience-facing role')
        require(item.get('role') != 'internal-production-note', 'Internal production instructions do not belong in creative artwork')
        if item['id'] in text_ids:
            require(nonempty(item.get('text')), 'Record actual visible words, including raster words')
        if item.get('claim') is True:
            kind = item.get('source_kind', 'external-research')
            placement = item.get('citation_placement', 'same-page')
            require(kind in {'brand-brief', 'external-research'}, 'Unknown claim source kind')
            if kind == 'brand-brief':
                require(placement == 'backend' and item.get('claim_scope') in
                        {'brand-identity', 'product-fact', 'brief-scenario'},
                        'Brand brief evidence belongs backstage and cannot cover external statistics')
                require(not item.get('visible_source'),
                        'Do not expose the competition brief as an audience-facing citation')
                require(nonempty(item.get('primary_source')), 'Brand facts still need a traceable primary source')
                bound_file(root, item['source_evidence'])
            elif placement == 'appendix':
                require(nonempty(item.get('visible_source')) and nonempty(item.get('primary_source')),
                        'Appendix citations need a readable source and primary-source locator')
                bound_file(root, item['source_evidence'])
                cited = artifact(root, item['citation_artifact'])
                require(len(cited) == 1, 'Identify the exact appendix page containing the citation')
                require(next(iter(cited))[:3] == next(iter(keys))[:3],
                        'Appendix citation must belong to the same current artifact/version')
                citation_record = load(bound_file(root, item['citation_render_record']))
                require(artifact(root, citation_record['source']) == cited and
                        item['citation_view'] in [v['file'] for v in citation_record['views']],
                        'Appendix citation view must bind the exact cited page')
                image_file(root, item['citation_view'])
                require(nonempty(item.get('reader_locator')), 'Appendix citations need a reader-facing locator')
            else:
                require(placement == 'same-page', 'External research cannot be hidden in backend evidence alone')
                require(nonempty(item.get('visible_source')) and nonempty(item.get('primary_source')),
                        'External claims need a same-page visible source and primary-source locator')
                bound_file(root, item['source_evidence'])
                require(item.get('source_view') in by_id, 'Claim source must be visible in a current render')
        if item.get('role') == 'required-disclosure':
            bound_file(root, item['rule_evidence'])
            require(nonempty(item.get('rule_quote')), 'In-artwork disclosure requires a specific rule basis')
    typography = unit['typography']
    require({r['element_id'] for r in typography} == text_ids and len(typography) == len(text_ids),
            'Every visible text object needs a final-render typography observation')
    for text in typography:
        require(text.get('detail_view') in {v['id'] for v in by_scale['detail']}, 'Typography requires a current detail crop')
        require(text.get('glyphs_complete') is True and text.get('optical_alignment') is True,
                'Glyph rendering and optical alignment must be checked in final pixels')
        require(isinstance(text.get('actual_lines'), int) and text['actual_lines'] > 0 and
                isinstance(text.get('max_lines'), int) and text['max_lines'] > 0, 'Declare actual and maximum line counts')
        intentional = text.get('intentional_line_exception')
        normal = (text['actual_lines'] <= text['max_lines'] and
                  (not text.get('no_wrap') or text['actual_lines'] == 1) and text.get('orphan_or_bad_break') is False)
        if not normal:
            require(isinstance(intentional, dict) and nonempty(intentional.get('design_reason')), 'Unexpected line break or orphan remains unresolved')
            decision = rows.get(intentional.get('decision_id'))
            require(decision and decision['decision'] == 'pass' and decision['stage'] in {'representative', 'final'} and
                    keys <= coverage(root, decision['reviewed_artifacts']), 'Poetic-line exception needs exact-version human content approval')
    containers = unit['containers']
    require({r['element_id'] for r in containers} == label_ids and len(containers) == len(label_ids),
            'Measure every embedded container; one repaired label cannot stand for its siblings')
    for label in containers:
        outer, safe, text = box(label['container_bounds']), box(label['safe_bounds']), box(label['text_bounds'])
        require(contains(outer, safe) and contains(safe, text), 'Text escaped its measured visual container')
        require(label['font_size'] >= label['minimum_font_size'] > 0 and label['actual_lines'] == label['expected_lines'],
                'Container fit cannot be obtained by unreadable shrinkage or unintended wrapping')
        require(label.get('semantic_anchor_verified') is True, 'Label lost its scene anchor')
        require(label.get('detail_view') in {v['id'] for v in by_scale['detail']}, 'Container fit needs a current crop')
        if label.get('alignment') == 'center-middle':
            tolerance = label['center_tolerance']
            require(isinstance(tolerance, (int, float)) and math.isfinite(tolerance) and tolerance >= 0,
                    'Center tolerance must be a project-specific finite nonnegative value')
            require(all(abs((text[i]+text[i+2]-safe[i]-safe[i+2])/2) <= tolerance for i in (0, 1)),
                    'Text center exceeds the declared container tolerance')
    products = unit['products']
    require({r['element_id'] for r in products} == product_ids and len(products) == len(product_ids),
            'Every visible product needs geometry, official asset and scene-integration evidence')
    for product in products:
        bound_file(root, product['official_asset'])
        require(product['actual_count'] == product['expected_count'] > 0, 'Generated product count drift')
        for key in ('aspect_ratio', 'relative_scale'):
            actual = product['actual_'+key]; interval = product['allowed_'+key]
            require(isinstance(actual, (int, float)) and math.isfinite(actual) and len(interval) == 2 and
                    0 < interval[0] <= actual <= interval[1], 'Product '+key+' violates the scene geometry contract')
        observations(product['checks'], PRODUCT_CHECKS, set(by_id), pending)
    for region in unit.get('preserved_regions', []):
        before = image_file(root, region['before']); after = image_file(root, region['after'])
        require(region['after']['sha256'] == native_view['file']['sha256'], 'Preserved-region check does not refer to the current render')
        bounds = box(region['bounds'])
        require(before.size == after.size and contains([0,0,after.width,after.height], bounds), 'Invalid preserved-region comparison')
        require(ImageChops.difference(before.crop(bounds), after.crop(bounds)).getbbox() is None,
                'Previously approved region changed during a local repair')
    return keys


def expand_checks(rows):
    """One concrete observation may cover related checks; no duplicate check IDs."""
    require(isinstance(rows, list), 'Visual observations must be a list')
    expanded = []
    for row in rows:
        names = row.get('covers', [row.get('check')])
        require(isinstance(names, list) and names and all(nonempty(n) for n in names),
                'A grouped observation needs explicit check coverage')
        expanded.extend(dict(row, check=name) for name in names)
    return expanded


def inspect_audience_tests(root, unit, keys):
    """Optional test records never arise from a qualitative acceptance checkbox."""
    tests = unit.get('audience_tests', [])
    require(isinstance(tests, list), 'audience_tests must be a list of bound records')
    for ref in tests:
        record = load(bound_file(root, ref))
        require(artifact(root, record['artifact']) == keys, 'Audience test must bind the reviewed version/unit')
        require(record.get('method') in {'timed-recall', 'untimed-comprehension'}, 'Unknown audience test method')
        require(nonempty(record.get('prompt')) and type(record.get('blinded')) is bool,
                'Record the actual prompt and whether the test was blinded')
        if record['method'] == 'timed-recall':
            duration = record.get('exposure_seconds')
            require(type(duration) in (int, float) and math.isfinite(duration) and duration > 0,
                    'A timed test needs its actual exposure duration')
        answers = record.get('responses')
        require(isinstance(answers, list) and answers and all(
            isinstance(a, dict) and nonempty(a.get('participant_id')) and nonempty(a.get('response')) for a in answers),
            'Keep actual participant responses; approval alone is not recall evidence')
        require(len({a['participant_id'] for a in answers}) == len(answers), 'Duplicate audience participant')
        bound_file(root, record['source'])


def inspect_proportional(root, unit, views, pending=None):
    """Validate applicable evidence, never infer that a model actually saw pixels."""
    def observed(row):
        require(nonempty(row.get('observation')), 'A concrete observation is required')
        refs = row.get('views')
        require(isinstance(refs, list) and refs and set(refs) <= set(views),
                'Observation must cite current pixel views')
        require(type(row.get('detail_required')) is bool, 'Record whether enlargement is necessary')
        if row['detail_required']:
            require(any(views[v]['scale'] == 'detail' for v in refs),
                    'Critical content needs a current detail view when not legible at native scale')
        require(any(views[v]['scale'] in {'native', 'detail'} for v in refs),
                'A thumbnail alone cannot verify critical content or repairs')

    critical = unit['critical_review']
    require(isinstance(critical, list), 'Critical review must be a list')
    required = {'key-text', 'brand-product', 'data-citations'}
    require(len(critical) == len(required) and {r.get('kind') for r in critical} == required,
            'Actively review key text, brand/product and data/citations on every page')
    for row in critical:
        require(row.get('status') in {'pass', 'not-applicable', 'pending', 'not-run'}, 'Critical content has failed or has an unknown status')
        observed(row)
        if row['status'] in {'pending', 'not-run'}:
            require(pending is not None, 'Critical content is unfinished')
            pending.append({'check': row['kind'], 'kind': 'work', 'reason': row['observation']})
        if row['status'] != 'not-applicable' and row['kind'] in {'brand-product', 'data-citations'}:
            evidence = row.get('evidence')
            require(isinstance(evidence, list) and evidence, 'Key facts need traceable evidence')
            for ref in evidence:
                bound_file(root, ref)
        if row['status'] != 'not-applicable' and row['kind'] == 'data-citations':
            require(nonempty(row.get('reader_locator')),
                    'External research needs a reader-facing citation locator')
    issues = unit['issues']
    require(isinstance(issues, list), 'Declare observed issues; an empty list means none observed')
    ids = set()
    for issue in issues:
        require(nonempty(issue.get('id')) and issue['id'] not in ids, 'Issue IDs must be unique')
        ids.add(issue['id'])
        require(nonempty(issue.get('problem')) and nonempty(issue.get('affected_scope')),
                'Record the observed problem and its affected scope')
        require(issue.get('status') == 'resolved', 'Observed issue remains unresolved: '+issue['problem']+
                '; scope='+issue['affected_scope']+'; return to '+str(issue.get('return_stage', 'the responsible creative/production stage')))
        observed(issue)
        # Measurements are conditional on a concrete need, not required for every object.
        for measure in issue.get('measurements', []):
            require(nonempty(measure.get('reason')) and nonempty(measure.get('unit')),
                    'A measurement needs a reason and unit')
            actual, lower, upper = measure['actual'], measure['minimum'], measure['maximum']
            require(all(type(v) in (int, float) and math.isfinite(v) for v in (actual, lower, upper))
                    and lower <= actual <= upper, 'Required measurement is outside its allowed interval')
    # Region reuse proves pixel stability only, not unchanged meaning or citations.
    from PIL import ImageChops
    native = next(v for v in views.values() if v['scale'] == 'native')
    for region in unit.get('preserved_regions', []):
        before, after = image_file(root, region['before']), image_file(root, region['after'])
        require(region['after']['sha256'] == native['file']['sha256'], 'Preserved-region check uses an old render')
        bounds = box(region['bounds'])
        require(before.size == after.size and contains([0, 0, after.width, after.height], bounds),
                'Invalid preserved-region comparison')
        require(ImageChops.difference(before.crop(bounds), after.crop(bounds)).getbbox() is None,
                'Previously approved region changed during a local repair')


def validate_pack_identity(pack, manifest):
    require(isinstance(pack, dict), 'Visual evidence must be an object')
    require(pack.get('schema_version') in ('1.0.0', '2.0.0', '2.1.0', '2.2.0','2.3.0','2.4.0','2.5.0'),
            'Visual evidence identity/scope mismatch: schema_version unsupported or missing; expected 1.0.0/2.0.0/2.1.0')
    for key in ('run_id', 'run_scope'):
        require(pack.get(key) == manifest[key],
                f'Visual evidence {key} mismatch: expected {manifest[key]!r}, actual {pack.get(key)!r}')
    require(isinstance(pack.get('units'), list) and bool(pack['units']),
            'Visual evidence units must be a nonempty array covering every declared unit; use the visual-review template')


def validate_visual_review(root, manifest):
    if manifest.get('schema_version') != '0.4.0' or manifest.get('category') not in {'print-ad', 'marketing-plan'} or manifest.get('run_scope') == 'concept-only':
        return []
    try:
        root = root.resolve()
        contract, rows = read_contract(root, manifest)
        pack = load(inside(root, manifest['artifacts']['visual_review']))
        validate_pack_identity(pack, manifest)
        secondary_marker = manifest.get('secondary_copy_contract')
        secondary = secondary_marker in {'print-secondary-copy-v1','print-secondary-copy-v2'}
        require('secondary_copy_contract' not in manifest or secondary, 'Unsupported secondary_copy_contract')
        scoped_secondary = secondary_marker == 'print-secondary-copy-v2'
        if manifest['category'] == 'print-ad' and manifest.get('artifacts', {}).get('quality_gate_results'):
            gates = load(inside(root, manifest['artifacts']['quality_gate_results']))
            require(gates.get('definition_set_id') != 'print-ad.0.16.0' or scoped_secondary,
                    'Current print-ad.0.16.0 requires scoped secondary_copy_contract print-secondary-copy-v2; no silent omission')
        secondary_version = '2.5.0' if scoped_secondary else '2.4.0'
        require(not secondary or pack['schema_version'] == secondary_version, 'Secondary copy requires visual evidence '+secondary_version)
        require(pack['schema_version'] not in {'2.4.0','2.5.0'} or secondary, 'Visual evidence requires secondary_copy_contract')
        if manifest.get('product_contract') in {'print-product-v1','print-product-v2'}:
            required_version = secondary_version if secondary else ('2.3.0' if manifest['product_contract']=='print-product-v2' else '2.2.0')
            require(pack['schema_version'] == required_version, 'Product/secondary visual evidence version mismatch')
        if manifest['run_scope'] == 'delivery-candidate':
            expected = coverage(root, contract['final_artifacts'])
        else:
            expected = set()
            cancelled = cancelled_requests(root, contract)
            selected = manifest.get('visual_review_request_ids')
            if selected is not None:
                require(isinstance(selected,list) and selected and all(isinstance(x,str) and x for x in selected)
                        and len(set(selected))==len(selected),'Select explicit unique current production request IDs')
                known={load(bound_file(root,r))['id'] for r in contract['production_requests']}
                require(set(selected)<=known and not set(selected)&set(cancelled),'Visual scope names unknown or cancelled requests')
            for ref in contract['production_requests']:
                request = load(bound_file(root, ref))
                if request['id'] not in cancelled and (selected is None or request['id'] in selected):
                    expected |= coverage(root, request['representatives'])
        require(expected, 'Visual evidence needs explicit production or delivery scope')
        actual = set(); pending = []; secondary_rows = []
        for unit in pack['units']:
            unit_pending = []
            keys = inspect_unit(root, unit, rows, manifest['category'], pack['schema_version'] != '1.0.0', unit_pending,
                                qualitative=pack['schema_version'] in {'2.1.0', '2.2.0','2.3.0','2.4.0','2.5.0'})
            if manifest.get('product_contract') in {'print-product-v1','print-product-v2'}:
                inspect_product_unit(root, unit)
                require(all(p['contract']==manifest['product_contract'] for p in unit['product_integration']),'Product evidence cannot downgrade current contract')
            if secondary:
                try:
                    require(unit.get('secondary_copy',{}).get('contract')==secondary_marker,
                            'Artwork secondary contract must match current manifest marker')
                    secondary_rows.append(inspect_secondary_copy(root, unit))
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                    raise SecondaryCopyError(str(exc)) from exc
            pending.extend(dict(item, units=unit['artifact']['units']) for item in unit_pending)
            require(not actual & keys, 'Duplicate reviewed visual unit')
            actual |= keys
        require(expected == actual, 'Visual evidence must cover every declared artwork/page, with no sample-to-full extrapolation')
        if secondary:
            try:
                inspect_secondary_series(secondary_rows, manifest.get('series_mode', 'single'))
            except (ValueError, KeyError, TypeError) as exc:
                raise SecondaryCopyError(str(exc)) from exc
            failures = [x for x in secondary_rows if not x['passed']]
            if failures:
                return [secondary_copy_result(failures), {'name':'final-pixel-evidence','passed':False,'core_failure':False,'return_to_stage':'production','repair_kind':'text-layer-repair','evidence':'Secondary copy needs local text repair and a new independent check'}]
        if pending:
            return [{'name': 'final-pixel-evidence', 'passed': False, 'state': 'in-progress',
                     'waiting_kind': 'human' if all(p['kind'] == 'human' for p in pending) else 'work',
                     'evidence': pending}]
        return [{'name':'final-pixel-evidence','passed':True,
                 'evidence':'Current render coverage and applicable evidence checked; record validation does not certify visual judgment, human approval or an audience experiment.',
                 'assessment_protocol': pack['schema_version'],
                 'audience_test_performed': 'not-inferred-from-check-status'}]
    except SecondaryCopyError as exc:
        return [secondary_copy_result([{'error':str(exc)}]), {'name':'final-pixel-evidence','passed':False,'core_failure':False,'return_to_stage':'production','repair_kind':'text-layer-repair','evidence':str(exc)}]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError) as exc:
        return [{'name':'final-pixel-evidence','passed':False,'evidence':str(exc)}]


PRODUCT_LABEL_QUESTION = '产品上的品牌/品类文字是否与官方一致、正向可读（不倒置、不镜像、无伪字）？'
PRODUCT_LOCAL_RUBRIC = PRODUCT_LABEL_QUESTION + '\n只核对提供的官方原图与当前局部像素；逐项记录品牌、可见品类文字与标识、遮挡及旧图残留。倾斜/透视允许，不要求包装细字缩略可读。不得根据作者解释补字或把正常端帽/弹簧判断为残留。'


def product_geometry_risk(geometry):
    """Map the actual reading vector embedded in the official raster to the final view."""
    angle = geometry['rotation_degrees']
    require(type(angle) in (int, float) and math.isfinite(angle), 'Register finite official-layer rotation')
    flips = [geometry[k] for k in ('flip_horizontal', 'flip_vertical')]
    require(all(type(v) is bool for v in flips), 'Register both official-layer flips')
    h = geometry['perspective_matrix']
    require(isinstance(h, list) and len(h) == 9 and all(type(v) in (int, float) and math.isfinite(v) for v in h),
            'Register nine finite perspective matrix entries')
    reading = geometry['official_reading_vector']
    require(isinstance(reading, list) and len(reading) == 2 and all(type(v) in (int,float) and math.isfinite(v) for v in reading)
            and math.hypot(*reading) > 0, 'Register official reading vector')
    samples = geometry['label_sample_points']
    require(isinstance(samples,list) and samples, 'Register label surface sample points')
    mirrored = flips[0] != flips[1]; angles = []
    rad = math.radians(angle); c,s = math.cos(rad),math.sin(rad)
    vx,vy = reading
    vx = -vx if flips[0] else vx; vy = -vy if flips[1] else vy
    vx,vy = c*vx-s*vy,s*vx+c*vy
    for point in samples:
        require(isinstance(point,list) and len(point)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in point),
                'Invalid label surface sample point')
        x,y=point; a,b,cc,d,e,f,g,hh,i=h; den=g*x+hh*y+i
        require(abs(den)>1e-12, 'Singular perspective at label')
        nx,ny=a*x+b*y+cc,d*x+e*y+f
        j00=(a*den-nx*g)/den**2; j01=(b*den-nx*hh)/den**2
        j10=(d*den-ny*g)/den**2; j11=(e*den-ny*hh)/den**2
        det=j00*j11-j01*j10
        require(abs(det)>1e-12, 'Degenerate label perspective')
        mirrored = mirrored or det < 0
        ox,oy=j00*vx+j01*vy,j10*vx+j11*vy
        # A portrait product photo may contain text rotated 90 degrees. Comparing
        # layer rotation alone misses e.g. +57 degrees becoming a +147 degree
        # visible reading direction. Normalize the source text, not the bottle axis.
        delta=math.degrees(math.atan2(oy,ox))
        angles.append(abs(delta))
    return {'mirrored':mirrored,'maximum_reading_rotation':max(angles),'inverted':max(angles)>90+1e-8}


def exact_pixel_diff(before, after, mask):
    """Zero tolerance, all decoded channels, count pixels rather than components."""
    from PIL import Image, ImageChops
    require(before.size == after.size == mask.size, 'Pixel comparison dimensions differ')
    require(before.mode == after.mode and before.mode in {'RGB','RGBA','L'}, 'Pixel comparison modes differ or unsupported')
    mask = mask.convert('L')
    require(set(mask.getdata()) <= {0,255}, 'Allowed mask must be binary; feathering is not an allowed-region definition')
    diff=ImageChops.difference(before,after)
    changed=Image.new('L',before.size,0)
    for channel in diff.split(): changed=ImageChops.lighter(changed,channel.point(lambda v:255 if v else 0))
    outside=ImageChops.multiply(changed,ImageChops.invert(mask))
    return {'changed_pixels':changed.histogram()[255], 'outside_changed_pixels':outside.histogram()[255],
            'difference_bounds':list(changed.getbbox()) if changed.getbbox() else None}


def product_triptych(root, record):
    """Deterministically derive the official / generated / final enlarged panels."""
    from PIL import Image
    panels=[]
    for role in ('official','generated','final'):
        panel=record['panels'][role]; source=image_file(root,panel['source']); bounds=box(panel['bounds'])
        require(all(type(v) is int for v in bounds) and contains([0,0,*source.size],bounds), 'Invalid triptych crop')
        zoom=panel['zoom']; require(type(zoom) in (int,float) and 1.5<=zoom<=4,'Triptych requires enlarged local crops')
        crop=source.crop(bounds); panels.append(crop.resize((round(crop.width*zoom),round(crop.height*zoom)),Image.Resampling.LANCZOS))
    sheet=Image.new('RGB',(sum(p.width for p in panels),max(p.height for p in panels)), 'white')
    offset=0
    for p in panels: sheet.paste(p,(offset,0)); offset+=p.width
    return sheet



INDEPENDENT_PRODUCT_SCENE_RUBRIC_V2 = "产品是否真正处于场景中（透视、遮挡、接触、光影一致），而非贴片？"

def validate_scene_product_plan(root, plan):
    from PIL import Image,ImageChops
    require(isinstance(plan,dict) and plan.get('contract')=='print-product-plan-v2','Missing preproduction product scene plan')
    require(nonempty(plan.get('element_id')) and nonempty(plan.get('choice_reason')),'Product plan needs identity and method reason')
    image_file(root,plan['official'])
    require(timestamp(plan['registered_at'])<=datetime.now(timezone.utc),'Invalid product plan registration time')
    role,method=plan.get('role'),plan.get('generation_method')
    require(role in {'scene-object','display-object'} and method in {'reference-edit-label-remap','official-asset-composite'},'Unknown product role/method in plan')
    if method=='official-asset-composite':
        require(role=='display-object' and nonempty(plan.get('display_reason')),'Paste must be registered as independent display-object with reason')
    if role=='scene-object':
        require(method=='reference-edit-label-remap' and nonempty(plan.get('container_contact_structure')),
                'Scene product plan needs official-reference edit and container/contact structure')
        size=plan['canvas_size']
        require(isinstance(size,list) and len(size)==2 and all(type(v) is int and v>0 for v in size),'Product plan needs canvas dimensions')
        masks=[]
        for key in ['edit_mask','container_contact_mask']:
            with Image.open(bound_file(root,plan[key])) as im: masks.append(im.convert('L'))
            require(list(masks[-1].size)==size and set(masks[-1].getdata())<={0,255} and masks[-1].getbbox() is not None,
                    'Product plan mask must be nonempty binary at planned canvas size')
        require(ImageChops.subtract(masks[1],masks[0]).getbbox() is None,'Preproduction mask must cover container/contact structure')
    return plan

def validate_product_dispatch_v2(root,manifest,request):
    """Require a plan before any declared product generation/edit, including local compositing."""
    operation=request.get('product_operation')
    require(operation in {'generate','edit','not-related'},'Production request must declare product_operation')
    targets=request.get('product_targets')
    require(isinstance(targets,list),'Production request must declare product_targets')
    require(all(isinstance(x,dict) and set(x)=={'element_id','role'} and nonempty(x['element_id'])
                and x['role'] in {'scene-object','display-object'} for x in targets)
            and len({x['element_id'] for x in targets})==len(targets),'Product targets need unique identities and roles')
    if operation=='not-related':
        require(not targets and 'product_plan_record' not in request,'not-related cannot generate/edit declared products')
        return
    require(targets,'Product generation/edit needs explicit product targets')
    ref=request.get('product_plan_record')
    record_path=bound_file(root,ref)
    require(record_path==inside(root,manifest['artifacts']['production_manifest']),'Plan must be in current production record')
    record=load(record_path)
    plans=record.get('product_scene_plans')
    require(isinstance(plans,list) and plans,'Missing preproduction product scene plans')
    ids=[p.get('element_id') for p in plans]
    require(len(ids)==len(set(ids)),'Duplicate product plan identities')
    prepared=timestamp(request.get('prepared_at'))
    require(prepared<=datetime.now(timezone.utc),'Invalid product request prepared_at')
    inputs={bound_file(root,r) for r in request.get('input_files',[])}
    for target in targets:
        matches=[p for p in plans if p.get('element_id')==target['element_id']]
        require(len(matches)==1,'Missing preproduction plan for product '+target['element_id'])
        p=validate_scene_product_plan(root,matches[0])
        require(p['role']==target['role'] and timestamp(p['registered_at'])<=prepared,'Product plan role/time differs from request')
        required=[p['official']]+([p['edit_mask'],p['container_contact_mask']] if p['role']=='scene-object' else [])
        require(all(bound_file(root,r) in inputs for r in required),'Bind official reference and planned masks as actual request inputs')

def validate_product_scene_comparison_v2(root,row,raw):
    """Bind every independent scene answer to deterministic official/generated/final triptychs."""
    from PIL import ImageChops
    triples=row.get('product_triptychs')
    require(isinstance(triples,list),'Every complete draft must register product triptychs')
    require(len({p['element_id'] for p in triples})==len(triples),'Duplicate scene review product')
    returned=raw['comparison'].get('product_scene')
    require(isinstance(returned,list) and len(returned)==len(triples),'Missing independent product-in-scene question')
    passed=True
    for p,answer in zip(triples,returned):
        require(set(p)=={'element_id','role','triptych'} and p['role'] in {'scene-object','display-object'},'Invalid scene review triptych declaration')
        require(isinstance(answer,dict) and set(answer)=={'element_id','role','triptych','answer','observation'}
                and all(answer[k]==p[k] for k in p) and type(answer['answer']) is bool and nonempty(answer['observation']),
                'Independent scene answer must preserve role, triptych and pixel observation')
        trip=load(bound_file(root,p['triptych']))
        require(trip['panels']['final']['source']==row['observed_image'],'Product scene triptych is not current draft')
        expected=product_triptych(root,trip);actual=image_file(root,trip['image'])
        require(expected.size==actual.size and ImageChops.difference(expected,actual).getbbox() is None,'Product scene triptych pixels do not match sources')
        if p['role']=='scene-object': passed=passed and answer['answer']
        else: require(answer['answer'] is True,'Display object must explicitly record scene question as inapplicable/pass')
    seventh=row['answers'].get('product_in_scene')
    require(isinstance(seventh,dict) and type(seventh.get('answer')) is bool and seventh['answer']==passed
            and 'product_scene' in seventh.get('comparison_evidence',[]),
            'Scene integration is a core question; individual failure cannot be offset')
    return passed


def inspect_product_record(root, product, current_ref):
    """Validate production evidence; geometric/record checks do not certify visual truth."""
    from PIL import Image, ImageChops
    require(product.get('contract') in {'print-product-v1','print-product-v2'},'Missing current product contract')
    if product.get('contract')=='print-product-v2':
        plan=validate_scene_product_plan(root,load(bound_file(root,product['preproduction_plan'])))
        require(plan['element_id']==product['element_id'] and plan['official']==product['official'] and plan['role']==product['role'] and plan['generation_method']==product['method'],'Production differs from preproduction product plan')
        if plan['role']=='scene-object':
            require(plan['edit_mask']==product['edit_mask'] and plan['container_contact_mask']==product['container_contact_mask'],
                    'Scene production masks differ from the registered preproduction plan')
    require(product['final']==current_ref,'Product review must bind current native pixels')
    official=image_file(root,product['official']); final=image_file(root,product['final'])
    require(nonempty(product.get('choice_reason')),'Record scene-specific production choice')
    role,method=product['role'],product['method']
    require(role in {'scene-object','display-object'},'Declare product scene role')
    require(method in {'reference-edit-label-remap','official-asset-composite'},'Unknown product production method')
    require(role!='scene-object' or method=='reference-edit-label-remap', 'Official paste cannot masquerade as a scene object')
    geometry=product['geometry']; risk=product_geometry_risk(geometry)
    bound_file(root,geometry['mapping_record'])
    require(product.get('glyphs_changed') is False and product.get('colors_changed') is False,
            'Official label glyphs and colors must remain unchanged; only geometry and neutral luminance blending allowed')
    require(nonempty(product.get('occlusion_observation')),'Record actual occlusion and brand readability')
    trip=load(bound_file(root,product['triptych']))
    require(trip['panels']['official']['source']==product['official'] and trip['panels']['final']['source']==product['final'],
            'Triptych official/final sources differ')
    generated=product['generated'] if method=='reference-edit-label-remap' else product['before']
    require(trip['panels']['generated']['source']==generated,'Triptych generated/intermediate source differs')
    expected=product_triptych(root,trip); actual=image_file(root,trip['image'])
    require(expected.size==actual.size and ImageChops.difference(expected,actual).getbbox() is None,'Triptych pixels differ from bound sources')
    items=trip['text_checks']
    require(isinstance(items,list) and items and any(r.get('kind')=='brand' for r in items),'Triptych needs item-by-item brand/category/mark checks')
    require(any(r.get('kind')=='category' for r in items) and any(r.get('kind')=='mark' for r in items),'Register category and mark, including genuine absence/occlusion')
    for item in items:
        require(nonempty(item.get('observation')) and nonempty(item.get('generated_observation')) and item.get('status') in {'pass','absent-on-official','occluded'},'Triptych label check failed or missing')
        if item['status']=='pass':
            require(nonempty(item.get('official_text')) and item['official_text']==item.get('final_text'),'Final label differs from official text/mark')
        if item.get('kind')=='brand': require(item['status']=='pass','Brand must remain clearly readable')
    independent=load(bound_file(root,product['independent_confirmation']))
    require(independent.get('checker_context')=='fresh-isolated' and nonempty(independent.get('checker_session_id'))
            and nonempty(independent.get('author_session_id')) and independent['checker_session_id']!=independent['author_session_id']
            and nonempty(independent.get('invocation_id')), 'Independent product confirmation cannot be an author self-check')
    require(independent['official']==product['official'] and independent['final']==product['final']
            and independent['triptych']==product['triptych'],'Independent confirmation uses stale product pixels')
    raw=load(bound_file(root,independent['raw_return']))
    require(raw==independent['result'] and raw['label_consistent_readable'] is True and nonempty(raw.get('label_observation')),
            'Independent product label check failed')
    require(timestamp(independent['started_at'])<=timestamp(independent['completed_at'])<=datetime.now(timezone.utc), 'Invalid independent product check time')
    if risk['mirrored'] or risk['inverted']:
        correction=product.get('orientation_correction')
        require(isinstance(correction,dict),'Inverted or mirrored official label requires corrected detail and independent confirmation')
        view=correction['detail']; crop=image_file(root,view['image']); bounds=box(view['bounds']); zoom=view['zoom']
        require(all(type(v) is int for v in bounds) and contains([0,0,*final.size],bounds) and 1.5<=zoom<=4,'Invalid corrected local enlargement')
        expected=final.crop(bounds).resize((round((bounds[2]-bounds[0])*zoom),round((bounds[3]-bounds[1])*zoom)),Image.Resampling.LANCZOS)
        require(view['source']==product['final'] and expected.size==crop.size and ImageChops.difference(expected,crop).getbbox() is None,
                'Orientation correction is not a current final detail')
        require(independent.get('corrected_detail')==view['image'] and raw.get('corrected_orientation_readable') is True
                and nonempty(correction.get('reason')), 'Orientation correction needs independent positive reading confirmation')
    proof=product['pixel_proof']
    require(proof['before']==product['before'] and proof['after']==product['final'],'Pixel proof baseline/final differs')
    before_path=bound_file(root,proof['before']); after_path=bound_file(root,proof['after'])
    with Image.open(before_path) as b,Image.open(after_path) as a,Image.open(bound_file(root,proof['allowed_mask'])) as m:
        measured=exact_pixel_diff(b,a,m)
    require(all(proof.get(k)==v for k,v in measured.items()),'Recorded pixel difference does not match actual pixels')
    require(measured['outside_changed_pixels']==0,'Pixels outside the edit mask changed')
    if method=='reference-edit-label-remap':
        image_file(root,product['generated'])
        require(product['generation_reference']==product['official'],'Scene edit must reference the official product asset')
        bound_file(root,product['edit_execution'])
        def mask(ref):
            with Image.open(bound_file(root,ref)) as im: result=im.convert('L')
            require(result.size==final.size and set(result.getdata())<={0,255},'Scene masks must be binary at final size')
            return result
        edit=mask(product['edit_mask']); contact=mask(product['container_contact_mask']); opening=mask(product['opening_mask']); allowed=mask(proof['allowed_mask'])
        require(contact.getbbox() is not None and opening.getbbox() is not None,'Container/contact and opening masks cannot be empty')
        require(ImageChops.subtract(contact,edit).getbbox() is None and ImageChops.subtract(opening,contact).getbbox() is None,
                'Small-mask redraw does not cover the container/contact structure')
        require(ImageChops.subtract(edit,allowed).getbbox() is None,'Editing mask escapes allowed region')
        with Image.open(bound_file(root,product['replacement_layer'])) as im:
            require(im.mode=='RGBA' and im.size==final.size,'Replacement layer must be RGBA at final dimensions')
            layer=im.copy()
        require(ImageChops.multiply(ImageChops.invert(layer.getchannel('A')),opening).getbbox() is None,
                'Old product pixels leak through opening; core must be fully opaque')
        require(ImageChops.multiply(ImageChops.difference(layer.convert('RGB'),final),Image.merge('RGB',(opening,opening,opening))).getbbox() is None,
                'Final opening differs from the replacement layer')
        require(raw.get('residue_absent') is True and nonempty(raw.get('residue_observation')),'Old product residue remains')
        require(raw.get('scene_integration') is True and nonempty(raw.get('scene_observation')),'Perspective/contact/light/occlusion does not fit the scene')
        require(product.get('boundary_on_natural_edge') is True,'Composite boundary must follow natural container edges')
    return {'geometry':risk,'pixel_difference':measured,'visual_judgment':'recorded independent observation; not machine certified'}


def inspect_product_unit(root, unit):
    record=load(bound_file(root,unit['render_record']))
    native=next(v['file'] for v in record['views'] if v['scale']=='native')
    require(type(unit.get('product_present')) is bool and nonempty(unit.get('product_presence_observation')),'Actively record whether products appear')
    products=unit['product_integration']
    require(isinstance(products,list) and bool(products)==unit['product_present'],'Every visible product needs production evidence')
    ids=[p['element_id'] for p in products]
    require(len(ids)==len(set(ids)),'Duplicate product integration IDs')
    for p in products: inspect_product_record(root,p,native)


INDEPENDENT_SECONDARY_COPY_RUBRIC_V1 = """只看当前成图与420px宽缩略图，判断次级文案：
次级文案可写可不写；画面和标题已交代产品与卖点，或多一行会削弱画面时可不写，不能把没有次级文案判为缺项。
写时只补画面和标题都给不了的信息（通常品牌/产品身份或一条官方事实），不复述标题、不解释画面在演什么；宁短勿全、语气克制、不堆功能词、不用广告腔。
字号、字重、颜色低于标题一级，与标题合成一个阅读区，不另起抢视线的文字组，位置看留白，不压人脸、关键动作或产品；在420px实际展示图上能读清。同系列结构、位置逻辑、字体处理统一。
“双鹿5号碱性电池｜电量飙升50%”在标题下方一行左对齐只是例子，不是默认或必需格式。第2–6项在未使用时不适用；官方包装细字不算另加的广告次级文案。
独立回答是否补充缺失信息、是否不复述标题、是否不解释画面、是否克制无广告腔、是否一个阅读区、颜色及位置是否从属、缩略图是否能读清，逐项给布尔与具体像素理由。
只看提供的图片，不根据作者解释补答案；图片判断不能认证官方来源，由生产记录核对。任一失败是文字层返工，不能推定核心创意失败；修改后绑定新图取得新独立检查。"""


class SecondaryCopyError(ValueError):
    pass


def secondary_copy_result(failures):
    return {'name':'secondary-copy-evidence','passed':False,'core_failure':False,
            'return_to_stage':'production','repair_kind':'text-layer-repair',
            'evidence':failures}


def secondary_type_metrics(runs):
    require(isinstance(runs,list) and runs, 'Secondary/title typography needs current text runs')
    for run in runs:
        require(nonempty(run.get('text')) and nonempty(run.get('font_family')) and nonempty(run.get('color')),
                'Text runs need visible words, font and color')
        require(all(type(run.get(k)) in (int,float) and math.isfinite(run[k]) and run[k]>0
                    for k in ['font_size_px','font_weight']) and run['font_weight']<=1000,
                'Text run typography must be finite and positive')
    # A mixed line is assessed as a whole: a short official fact may share the
    # title's weight, provided the character-weighted line weight is lower.
    weights=[max(1,sum(not c.isspace() for c in r['text'])) for r in runs]
    return {'minimum_size':min(r['font_size_px'] for r in runs),
            'maximum_size':max(r['font_size_px'] for r in runs),
            'maximum_weight':max(r['font_weight'] for r in runs),
            'mean_weight':sum(r['font_weight']*w for r,w in zip(runs,weights))/sum(weights)}


def inspect_secondary_copy(root, unit):
    from PIL import Image,ImageChops
    record=unit.get('secondary_copy')
    require(isinstance(record,dict) and record.get('contract') in {'print-secondary-copy-v1','print-secondary-copy-v2'},
            'Every current artwork needs secondary_copy usage and reason')
    require(type(record.get('used')) is bool and nonempty(record.get('reason')),
            'Secondary copy used/unused needs one concrete reason')
    kinds={'hierarchy','thumbnail_legibility','series_consistency','copy_semantics'}
    statuses=record.get('checks')
    require(isinstance(statuses,dict) and set(statuses)==kinds, 'Record all secondary copy checks')
    identity=unit['artifact']['units']
    scoped=record['contract']=='print-secondary-copy-v2'
    scope=secondary_element_scope(root,unit) if scoped else None
    if not record['used']:
        require(all(x=='not-applicable' for x in statuses.values()), 'Unused secondary checks must be not-applicable')
        require(not any(k in record for k in ['text','runs','official_sources','independent_review']),
                'Unused secondary copy cannot contain a hidden used-copy record')
        return dict(units=identity,used=False,passed=True,checks=statuses,reason=record['reason'])
    require(all(x in {'pass','fail'} for x in statuses.values()), 'Used secondary copy checks cannot be not-applicable')
    require(nonempty(record.get('text')) and ''.join(r['text'] for r in record['runs'])==record['text'],
            'Register actual secondary copy content and matching text runs; no format template')
    sources=record.get('official_sources')
    require(isinstance(sources,list) and sources, 'Used secondary copy needs official source')
    for source in sources:
        require(nonempty(source.get('locator')) and source.get('information_kind') in {'official-fact','brief-required-info'},
                'Secondary copy sources must locate official facts or brief requirements')
        bound_file(root,source['file'])
    title=secondary_type_metrics(record['title_runs']);copy=secondary_type_metrics(record['runs'])
    require(copy['maximum_size']<title['minimum_size'] and copy['maximum_weight']<=title['maximum_weight']
            and copy['mean_weight']<title['mean_weight'], 'Secondary copy hierarchy must be below title size and whole-line weight')
    views=load(bound_file(root,unit['render_record']))['views']; by_id={v['id']:v for v in views}
    native=next(v for v in views if v['scale']=='native');thumb=by_id[record['thumbnail_view']]
    require(thumb['scale']=='thumbnail', 'Secondary readability must cite actual thumbnail')
    ni=image_file(root,native['file']);ti=image_file(root,thumb['file'])
    require(ti.width==420 and ni.width>420, 'Secondary readability needs current 420px-wide preview')
    expected=ni.copy();expected.thumbnail((420,round(ni.height*420/ni.width)),Image.Resampling.LANCZOS)
    require(expected.size==ti.size and ImageChops.difference(expected,ti).getbbox() is None,
            'Secondary thumbnail is not current render pixels')
    threshold=record.get('minimum_display_font_px')
    require(type(threshold) in (int,float) and math.isfinite(threshold) and threshold>=10,
            'Declare reproducible display-font floor at least 10px; not a substitute for actual reading')
    display_minimum=copy['minimum_size']*ti.width/ni.width
    require(display_minimum>=threshold, 'Secondary copy is unreadable by declared 420px display-font floor')
    require(nonempty(record.get('reading_area')) and nonempty(record.get('series_id')),
            'Secondary copy needs shared title reading area and series identity')
    style=record.get('series_style')
    require(isinstance(style,dict) and set(style)=={'structure','placement_logic','font_treatment'}
            and all(nonempty(x) for x in style.values()), 'Record secondary series structure, placement logic and font treatment')
    independent=load(bound_file(root,record['independent_review']))
    require(independent.get('checker_context')=='fresh-isolated' and nonempty(independent.get('checker_session_id'))
            and nonempty(independent.get('author_session_id')) and independent['checker_session_id']!=independent['author_session_id']
            and nonempty(independent.get('invocation_id')), 'Independent secondary check cannot be author self-check')
    require(independent.get('rubric_version')==record['contract'] and independent.get('native')==native['file']
            and independent.get('thumbnail')==thumb['file'], 'Independent secondary check must bind current native and thumbnail')
    request=bound_file(root,independent['request']).read_text(encoding='utf-8')
    require(request==(INDEPENDENT_SECONDARY_COPY_RUBRIC_V2 if scoped else INDEPENDENT_SECONDARY_COPY_RUBRIC_V1), 'Independent secondary check must use fixed rubric without author explanations')
    expected_inputs=[native['file'],thumb['file']]
    if scoped:
        scope_file=independent.get('scope')
        require(isinstance(scope_file,dict), 'Independent secondary scope is required')
        require(load(bound_file(root,scope_file))==scope, 'Independent secondary scope differs from current role-bound elements')
        expected_inputs.append(scope_file)
    require(independent.get('inputs')==expected_inputs, 'Independent secondary inputs must be only current artwork, thumbnail and declared element scope')
    raw=load(bound_file(root,independent['raw_return']))
    require(raw==independent.get('result'), 'Independent secondary result differs from raw return')
    questions=['secondary_copy_present','supplements_missing_information','does_not_repeat_title','does_not_explain_picture',
               'restrained_not_advertising_tone','one_reading_area','subordinate_color_and_position','thumbnail_readable']
    extra={'scope_sha256','assessed_element_ids','out_of_scope_observations'} if scoped else set()
    if scoped:
        require(raw.get('scope_sha256')==scope_file['sha256'] and raw.get('assessed_element_ids')==record['element_ids'],
                'Independent secondary return must bind exactly the declared secondary elements and scope hash')
        require(isinstance(raw.get('out_of_scope_observations'),list), 'Save other-text opinions separately as information only')
        require(all(isinstance(x,dict) and nonempty(x.get('element_id')) and nonempty(x.get('observation'))
                    and x['element_id'] in {e['element_id'] for e in unit['text_elements'] if e['role']!='secondary-copy'}
                    for x in raw['out_of_scope_observations']), 'Other-text opinions must identify non-secondary elements')
    require(set(raw)==set(questions)|{'observation'}|extra and all(type(raw[k]) is bool for k in questions)
            and nonempty(raw.get('observation')), 'Independent secondary check needs all questions and concrete observation')
    require(timestamp(independent['started_at'])<=timestamp(independent['completed_at'])<=datetime.now(timezone.utc),
            'Independent secondary check timestamps invalid')
    if 'rework' in record:
        repair=record['rework'];old=load(bound_file(root,repair['previous_independent_review']))
        require(repair.get('kind')=='text-layer-repair' and repair['after']==native['file']
                and independent['invocation_id']!=old['invocation_id']
                and timestamp(independent['started_at'])>timestamp(old['completed_at']),
                'Text local repair needs new current independent check after previous return')
        before=image_file(root,repair['before']);after=image_file(root,repair['after'])
        require(old['native']==repair['before'], 'Text repair before pixels differ from saved old check')
        with Image.open(bound_file(root,repair['allowed_mask'])) as im:mask=im.copy()
        require(exact_pixel_diff(before,after,mask)['outside_changed_pixels']==0, 'Text repair changed protected non-text pixels')
    failed=[k for k in questions if raw[k] is not True]
    return dict(units=identity,used=True,passed=not failed,failed_questions=failed,core_failure=False,
                repair_kind='text-layer-repair',independent_review=record['independent_review'],observation=raw['observation'],
                series_id=record['series_id'],series_style=style,
                font_treatment=[(r['font_family'],r['font_weight'],r['font_size_px']/title['minimum_size'],r['color']) for r in record['runs']],
                minimum_display_font_px=display_minimum,out_of_scope_observations=raw.get('out_of_scope_observations',[]),measurement_limit='Declared renderer typography, current scaled pixels and independent actual reading; not an audience test')


def inspect_secondary_series(rows, series_mode):
    groups={}
    for row in rows:
        if row['used']:groups.setdefault(row['series_id'],[]).append(row)
    if series_mode=='series':
        require(len(groups)<=1, 'One declared series cannot split secondary style IDs to bypass consistency')
        for group in groups.values():
            baseline=group[0]
            require(all(x['series_style']==baseline['series_style'] and x['font_treatment']==baseline['font_treatment'] for x in group),
                    'Secondary copy series structure, placement logic or font treatment is inconsistent')
    return True


INDEPENDENT_SECONDARY_COPY_RUBRIC_V2 = """平面次级文案独立检查 print-secondary-copy-v2。
只看当前完整作品native、420px缩略图和绑定这些像素的文字元素范围。只评价范围中role=secondary-copy的指定element_ids、实际文字；以范围中的headline作层级参照。给出的文字/位置只标识范围，不是作者解释。不要把页脚的命题必需信息、产品事实限定、防误导说明、法定/官方小字、品牌与产品标识当成次级文案。
次级文案可写可不写；画面与标题已交代产品和卖点，或多一行削弱画面，可不写。不得把没有次级文案判为缺项。没有指定次级文案时第2–6项不适用，不失败。
写时只补画面和标题都给不了的信息，通常是品牌/产品身份或一条官方事实；不复述标题，不解释画面在演什么。只用官方事实或命题信息，宁短勿全、语气克制，不堆功能词、不用广告腔。看图不能认证来源，由生产记录核对。
字号、整行字重、颜色低于标题一级，与标题合成一个阅读区；位置看留白，不压人脸、关键动作和产品。在420px实际展示尺寸上能读清。同系列结构、位置逻辑、字体处理统一。以上第2–6项只判指定次级文案，不对页脚或其他文字区应用“不解释画面”和“420px可读”；页脚解释性内容不由此原则判，既有页脚规则继续原样执行。
“双鹿5号碱性电池｜电量飙升50%”在标题下方一行左对齐只是示例，不是默认或必需格式。
逐项返回secondary_copy_present、supplements_missing_information、does_not_repeat_title、does_not_explain_picture、restrained_not_advertising_tone、one_reading_area、subordinate_color_and_position、thumbnail_readable布尔以及具体像素理由observation，绑定scope_sha256、assessed_element_ids。只把指定次级文案失败列为文字层返工，不能推定核心创意失败。对其他文字区的意见单列out_of_scope_observations（element_id、observation），仅供信息记录，不改变上述答案，也不触发次级文案返工。不得根据作者解释补答案；修改后绑定新图并取得新的独立检查。"""


def secondary_element_scope(root,unit):
    """Select actual secondary elements, never auxiliary/footer text by default."""
    record=unit['secondary_copy'];elements=unit.get('text_elements')
    require(isinstance(elements,list) and elements, 'Current artwork needs text_elements with explicit roles')
    roles={'headline','secondary-copy','footer-required-or-fact','brand-product-mark','scene-text'}
    ids=[]
    native=next(x for x in load(bound_file(root,unit['render_record']))['views'] if x['scale']=='native')
    image=image_file(root,native['file'])
    for e in elements:
        require(isinstance(e,dict) and nonempty(e.get('element_id')) and e.get('role') in roles and nonempty(e.get('text')),
                'Text elements need unique identity, allowed role and actual text')
        box=e.get('bounds');require(isinstance(box,list) and len(box)==4 and all(type(n) in (int,float) and math.isfinite(n) for n in box)
                and 0<=box[0]<box[2]<=image.width and 0<=box[1]<box[3]<=image.height, 'Text element native bounds must be inside current pixels')
        ids.append(e['element_id'])
    require(len(set(ids))==len(ids), 'Text element IDs must be unique')
    selected=[e for e in elements if e['role']=='secondary-copy']
    require(record.get('element_ids')==[e['element_id'] for e in selected] and record['used']==bool(selected),
            'Secondary element_ids and usage must exactly match secondary-copy roles')
    titles=record.get('title_element_ids')
    require(isinstance(titles,list) and titles and len(set(titles))==len(titles), 'Declare title_element_ids for hierarchy reference')
    by_id={e['element_id']:e for e in elements}
    require(all(k in by_id and by_id[k]['role']=='headline' for k in titles), 'Title references must identify headline roles')
    require(titles==[e['element_id'] for e in elements if e['role']=='headline'],
            'Title references must include every headline element for hierarchy')
    if selected:
        require(record.get('runs')==[r for e in selected for r in e.get('runs',[])]
                and record.get('text')==''.join(e['text'] for e in selected)
                and record.get('title_runs')==[r for k in titles for r in by_id[k].get('runs',[])],
                'Secondary/title typography must match selected role-bound text elements')
        for e in selected+[by_id[k] for k in titles]:
            require(''.join(r['text'] for r in e.get('runs',[]))==e['text'], 'Element runs must match actual text')
    return dict(contract='print-secondary-copy-scope-v2',native=native['file'],
                element_ids=record['element_ids'],title_element_ids=titles,
                text_elements=[{k:e[k] for k in ['element_id','role','text','bounds']} for e in elements])
