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


def validate_visual_review(root, manifest):
    if manifest.get('schema_version') != '0.4.0' or manifest.get('category') not in {'print-ad', 'marketing-plan'} or manifest.get('run_scope') == 'concept-only':
        return []
    try:
        root = root.resolve()
        contract, rows = read_contract(root, manifest)
        pack = load(inside(root, manifest['artifacts']['visual_review']))
        require(pack.get('schema_version') in {'1.0.0', '2.0.0', '2.1.0'} and pack.get('run_id') == manifest['run_id'] and
                pack.get('run_scope') == manifest['run_scope'], 'Visual evidence identity/scope mismatch')
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
        actual = set(); pending = []
        for unit in pack['units']:
            unit_pending = []
            keys = inspect_unit(root, unit, rows, manifest['category'], pack['schema_version'] != '1.0.0', unit_pending,
                                qualitative=pack['schema_version'] == '2.1.0')
            pending.extend(dict(item, units=unit['artifact']['units']) for item in unit_pending)
            require(not actual & keys, 'Duplicate reviewed visual unit')
            actual |= keys
        require(expected == actual, 'Visual evidence must cover every declared artwork/page, with no sample-to-full extrapolation')
        if pending:
            return [{'name': 'final-pixel-evidence', 'passed': False, 'state': 'in-progress',
                     'waiting_kind': 'human' if all(p['kind'] == 'human' for p in pending) else 'work',
                     'evidence': pending}]
        return [{'name':'final-pixel-evidence','passed':True,
                 'evidence':'Current render coverage and applicable evidence checked; record validation does not certify visual judgment, human approval or an audience experiment.',
                 'assessment_protocol': pack['schema_version'],
                 'audience_test_performed': 'not-inferred-from-check-status'}]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError) as exc:
        return [{'name':'final-pixel-evidence','passed':False,'evidence':str(exc)}]
