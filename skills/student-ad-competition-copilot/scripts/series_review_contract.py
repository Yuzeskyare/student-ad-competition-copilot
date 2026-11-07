"""Bind the existing human series gate to the current ordered artwork set.

Observations are not human decisions. This validates evidence, not aesthetics.
"""
import copy
from datetime import datetime, timezone
from review_contract import bound_file, load, human_source, timestamp, inside
from user_decision_contract import effective_series_plan

REVISION = 'print-series-evidence-v1'
GATE = 'print-ad.series-increment'
CHECKS = ('shared-mechanism', 'real-variation', 'information-increment')
PREVIEW_LAYOUT = dict(kind='ordered-series-preview-v1', columns=3, cell_width=600, cell_height=830,
                      image_height=800, background='white', resample='LANCZOS', labels='ordinal')


def require(value, message):
    if not value:
        raise ValueError(message)


def applies(manifest):
    return (manifest.get('category') == 'print-ad' and manifest.get('series_mode') == 'series'
            and manifest.get('run_scope') != 'concept-only')


def current_members(root, manifest):
    """Project the existing current selection; never accept a caller member list."""
    plan = effective_series_plan(root, manifest)
    units = plan.get('units', [])
    require(units and len(set(units)) == len(units), 'Series needs unique effective units')
    review = manifest.get('core_creative_review', {})
    ids = review.get('current_assessment_ids', [])
    require(len(ids) == len(set(ids)), 'Duplicate current assessment IDs')
    rows = review.get('assessments', [])
    selected = []
    for ident in ids:
        matches = [r for r in rows if r.get('id') == ident]
        require(len(matches) == 1, 'Unknown or duplicate current assessment ID')
        selected.append(matches[0])
    members = {}
    for row in selected:
        art, image = row['artifact'], row['observed_image']
        require(len(art.get('units', [])) == 1, 'One current artwork per series member')
        unit = art['units'][0]
        if unit not in units and manifest.get('delivery_scope_selection'):
            continue
        require(unit in units and unit not in members, 'Unexpected or duplicate series member')
        bound_file(root, art); bound_file(root, image)
        members[unit] = dict(unit=unit, artifact={k: art[k] for k in ('path', 'sha256', 'version', 'units')},
                             image={k: image[k] for k in ('path', 'sha256')})
    # A production candidate may legitimately contain only its first member.
    return [members[u] for u in units if u in members], units


def validate_observations(root, ref, members):
    matrix = load(bound_file(root, ref))
    require(matrix.get('kind') == 'series-invariant-variable-increment-matrix-v1',
            'Single-artwork or direction reports cannot serve as series observations')
    require(matrix.get('members') == members, 'Series observations use a different set/order/version')
    require(matrix.get('observer_type') in {'author', 'independent-model'},
            'Precheck observations must not impersonate a human decision')
    rows = matrix.get('observations', [])
    units = [m['unit'] for m in members]
    require([r.get('unit') for r in rows] == units, 'Observe every current series member in order')
    for row in rows:
        require(all(isinstance(row.get(k), str) and row[k].strip()
                    for k in ('visible_relation', 'increment', 'pixel_evidence')),
                'Each member needs visible relation, increment and actual pixel evidence')
        require(row.get('compared_with') == [u for u in units if u != row['unit']],
                'Series observations must compare against the other current members')
    checks = matrix.get('checks', {})
    require(set(checks) == set(CHECKS), 'Use the three existing series checks')
    for item in checks.values():
        require(item.get('status') in {'supported', 'concern'} and isinstance(item.get('observation'), str)
                and item['observation'].strip(), 'Series precheck needs actual observations')
    if matrix.get('observer_type') == 'independent-model':
        require(isinstance(matrix.get('provenance'), dict), 'Independent observations need actual return provenance')
        bound_file(root, matrix['provenance'])
    return matrix


def render_preview(root, members):
    """Deterministic layout only; no visual quality or language judgments."""
    from PIL import Image, ImageOps, ImageDraw
    require(bool(members), 'A series preview needs current members')
    columns = min(PREVIEW_LAYOUT['columns'], len(members))
    canvas = Image.new('RGB', (columns * 600, ((len(members)+columns-1)//columns)*830), 'white')
    draw = ImageDraw.Draw(canvas)
    for index, member in enumerate(members):
        with Image.open(bound_file(root, member['image'])) as source:
            image = ImageOps.exif_transpose(source).convert('RGBA')
            image.thumbnail((600,800), Image.Resampling.LANCZOS)
        x, y = (index % columns)*600, (index // columns)*830
        canvas.paste(image, (x+(600-image.width)//2, y+(800-image.height)//2), image)
        draw.text((x+8,y+807), str(index+1), fill='black')
    return canvas


def validate_preview(root, record, members):
    from PIL import Image
    require(record.get('preview_build') == dict(layout=PREVIEW_LAYOUT, members=members),
            'Series preview needs its exact current members, order and deterministic layout')
    expected = render_preview(root, members)
    with Image.open(bound_file(root, record.get('contact_sheet'))) as actual:
        require(actual.mode == 'RGB' and actual.size == expected.size and actual.tobytes() == expected.tobytes(),
                'Series preview pixels differ from the complete current ordered members')


def review_result(root, manifest):
    """One shared consumer for receipts, content acceptance and gate validation."""
    if not applies(manifest):
        return dict(status='not-applicable', passed=True)
    try:
        members, units = current_members(root, manifest)
        ref = manifest.get('series_review')
        if ref is None:
            return dict(status='members-in-progress' if len(members) != len(units) else 'unreviewed',
                        passed=False, members=members, expected_units=units)
        record = load(bound_file(root, ref))
        require(record.get('kind') == REVISION, 'Missing or unknown series evidence revision')
        require(len(members) == len(units) and record.get('members') == members,
                'Series review is stale or does not cover the complete current ordered set')
        require(record.get('planned_units') == units, 'Series review belongs to a different effective scope')
        require(timestamp(record.get('prepared_at')) <= datetime.now(timezone.utc), 'Future series preparation')
        validate_preview(root, record, members)
        matrix = validate_observations(root, record.get('matrix'), members)
        decision = record.get('decision')
        base = dict(members=members, expected_units=units, observations=matrix['checks'], evidence=ref)
        if decision is None:
            return dict(status='awaiting-human', passed=False, **base)
        require(decision.get('kind') == 'series-human-decision-v1', 'Use a distinct whole-series human decision')
        require(decision.get('reviewed_members') == members, 'Human decision has different series coverage')
        at = human_source(root, decision.get('source'), decision.get('quote'))
        require(timestamp(record['prepared_at']) <= at == timestamp(decision.get('decided_at')) <= datetime.now(timezone.utc),
                'Human series decision must follow this prepared comparison and preserve its real event time')
        source = load(bound_file(root, decision['source']))
        # Same scope is bound in the exported source/context, not guessed from "pass".
        require(source.get('reviewed_series') == record.get('prepared_review'),
                'Human source/context must identify the exact presented prepared series')
        prepared = load(bound_file(root, record.get('prepared_review')))
        require(prepared.get('decision') is None and
                prepared == {k: v for k, v in record.items() if k != 'prepared_review'} | {'decision': None},
                'Human decision may only extend the immutable prepared comparison')
        checks = decision.get('checks', {})
        require(set(checks) == set(CHECKS), 'Human series decision must cover the existing three checks')
        for item in checks.values():
            require(type(item.get('passed')) is bool and isinstance(item.get('observation'), str)
                    and item['observation'].strip(), 'Preserve the human decision and its scope-specific rationale')
        success = all(c['passed'] for c in checks.values())
        return dict(status='pass' if success else 'fail', passed=success, decision=decision, **base)
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        return dict(status='invalid', passed=False, error=str(exc))


def content_check(root, manifest):
    result = review_result(root, manifest)
    if applies(manifest):
        try:
            gates = load(inside(root, manifest['artifacts']['quality_gate_results']))
            rows = [r for r in gates['results'] if r.get('gate_id') == GATE]
            require(len(rows) == 1 and gate_check(root, manifest, rows[0])[0], 'Series gate and current group evidence disagree')
        except (ValueError, KeyError, TypeError, OSError) as exc:
            result = dict(status='invalid', passed=False, error=str(exc))
    check = dict(name='series-increment-evidence', passed=result['passed'], evidence=result)
    if result['status'] in {'members-in-progress', 'unreviewed', 'awaiting-human'}:
        check.update(state='in-progress', stage='series',
                     waiting_kind='human' if result['status'] == 'awaiting-human' else 'work')
    return check


def gate_check(root, manifest, gate):
    result = review_result(root, manifest)
    if not applies(manifest):
        return True, result
    status = result['status']
    declared = gate.get('status')
    if status in {'invalid', 'not-applicable'}:
        return False, result
    if status in {'members-in-progress', 'unreviewed'}:
        return declared in {'not-run', 'in-progress'} and not gate.get('passed_check_ids') and not gate.get('failed_check_ids'), result
    bound = manifest['series_review']['path'] in gate.get('evidence_paths', [])
    if status == 'awaiting-human':
        return bound and declared == 'in-progress' and not gate.get('passed_check_ids') and not gate.get('failed_check_ids'), result
    decision = result['decision']
    passed = {k for k, v in decision['checks'].items() if v['passed']}
    failed = set(CHECKS) - passed
    correct = (bound and declared == status and set(gate.get('passed_check_ids', [])) == passed and
               set(gate.get('failed_check_ids', [])) == failed and
               gate.get('checked_at') == decision['decided_at'] and
               gate.get('reviewers') == [dict(type='human', source=decision['source']['path'])])
    return correct, result


def attach(root, manifest, record, directory):
    """Write new evidence and snapshots; never overwrite historical gate results."""
    from review_workflow import write
    m = copy.deepcopy(manifest)
    m['series_review'] = write(root, directory/'series-review.json', record)
    result = review_result(root, m)
    require(result['status'] not in {'invalid', 'unreviewed', 'members-in-progress'}, str(result))
    gates = copy.deepcopy(load(inside(root, m['artifacts']['quality_gate_results'])))
    rows = [r for r in gates['results'] if r.get('gate_id') == GATE]
    require(len(rows) == 1, 'One existing series gate is required')
    gate = rows[0]
    decision = result.get('decision')
    gate.update(status=result['status'] if decision else 'in-progress',
                passed_check_ids=[k for k in CHECKS if decision and decision['checks'][k]['passed']],
                failed_check_ids=[k for k in CHECKS if decision and not decision['checks'][k]['passed']],
                reviewers=[dict(type='human', source=decision['source']['path'])] if decision else [],
                checked_at=decision['decided_at'] if decision else record['prepared_at'],
                evidence_paths=[m['series_review']['path']], boundaries=[], waiver_reason=None)
    gate.setdefault('notes', None)
    m['artifacts']['quality_gate_results'] = write(root, directory/'quality-gates.json', gates)['path']
    require(gate_check(root, m, gate)[0], 'Series evidence and gate disagree')
    return dict(manifest=write(root, directory/'manifest.json', m), review=m['series_review'], result=result)


def prepare_review(root, manifest, contact_sheet=None, matrix=None):
    from review_workflow import allocate
    from workflow_runtime import now
    m = load(bound_file(root, manifest))
    require(applies(m), 'Use series review only for a declared series')
    members, units = current_members(root, m)
    require(len(members) == len(units), 'Finish the current series members before preparing whole-series review')
    validate_observations(root, matrix, members)
    preview_build = dict(layout=PREVIEW_LAYOUT, members=members)
    if contact_sheet is not None:
        # Optional existing preview must match; it cannot silently be substituted.
        validate_preview(root, dict(contact_sheet=contact_sheet, preview_build=preview_build), members)
    directory = allocate(root, 'series-review')
    sheet = directory/'contact-sheet.png'
    sheet.parent.mkdir(parents=True, exist_ok=True)
    render_preview(root, members).save(sheet)
    from review_contract import digest
    contact_sheet = dict(path=sheet.relative_to(root).as_posix(), sha256=digest(sheet))
    record = dict(kind=REVISION, members=members, planned_units=units, contact_sheet=contact_sheet, preview_build=preview_build,
                  matrix=matrix, prepared_at=now(), decision=None)
    return attach(root, m, record, directory)


def decide_review(root, manifest, source, quote, checks):
    from review_workflow import allocate
    m = load(bound_file(root, manifest))
    result = review_result(root, m)
    require(result['status'] in {'awaiting-human', 'pass', 'fail'}, 'Prepare a valid current group comparison first')
    record = copy.deepcopy(load(bound_file(root, m['series_review'])))
    original = record.get('prepared_review', m['series_review'])
    at = human_source(root, source, quote)
    if record.get('decision'):
        require(at > timestamp(record['decision']['decided_at']), 'A new human decision must be later; retain the old snapshot')
    record.update(prepared_review=original, decision=dict(kind='series-human-decision-v1', source=source,
        quote=quote, decided_at=at.isoformat(), reviewed_members=record['members'], checks=checks))
    return attach(root, m, record, allocate(root, 'series-decision'))
