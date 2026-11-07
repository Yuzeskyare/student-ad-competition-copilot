"""Reuse track prerequisites at dispatch; never infer meaning from prose."""
from review_contract import inside, load
from quality_gate_contract import validate_quality_gate_results


def validate_print_preproduction(root, manifest, request):
    # AI declares the work stage. Never infer it from a prompt or filename.
    stage = request.get('production_stage', 'artwork')
    if stage not in {'prototype', 'prototype-repair', 'artwork'}:
        raise ValueError('Unknown print production_stage')
    path = inside(root, manifest['artifacts']['quality_gate_results'])
    results = load(path)
    gates = {'print-ad.brief-evidence', 'print-ad.direction-distinctness'}
    prototype = 'print-ad.visual-relation-prototype'
    if stage == 'artwork':
        gates.add(prototype)
    else:
        rows = [r for r in results['results'] if r.get('gate_id') == prototype]
        allowed = {'not-run', 'in-progress'} if stage == 'prototype' else {'fail'}
        if len(rows) != 1 or rows[0].get('status') not in allowed:
            raise ValueError('Prototype stage must match its recorded unfinished/failed gate')
    checks = validate_quality_gate_results(root, path, 'print-ad', manifest.get('run_id'),
        gates, manifest=manifest, prerequisite_only=True)
    from visual_generation_capability_contract import validate_visual_generation_capability
    scope = manifest.get('run_scope')
    checks += validate_visual_generation_capability(manifest,
        scope if scope in {'production-candidate', 'delivery-candidate'} else 'production-candidate', root)
    failed = [c['name'] for c in checks if not c['passed']]
    if failed:
        raise ValueError('Print production prerequisites failed: ' + ', '.join(failed))
    return checks


def validate_preproduction(root, manifest, request):
    track = manifest.get('category')
    if track not in {'ad-copy', 'marketing-plan'}:
        raise ValueError('Unknown production track')
    # Concept-only is a preparation scope; it cannot authorize a production
    # request. Ordinary research/helper commands do not call this entry.
    if manifest.get('run_scope') not in {'production-candidate', 'delivery-candidate'}:
        raise ValueError('Formal dispatch needs a production scope, not concept-only preparation')
    if track == 'ad-copy':
        from validate_ad_copy_run import RUN_SCOPE_GATES
    else:
        from validate_marketing_plan_run import RUN_SCOPE_GATES
    artifacts = manifest.get('artifacts', {})
    constraints = load(inside(root, artifacts.get('brief_constraints')))
    if (track == 'marketing-plan' and constraints.get('category_authorized') is not True
            or constraints.get('category_authorized') is False):
        raise ValueError('Production category is not authorized by the brief')
    concept = load(inside(root, artifacts.get('concept_gate')))
    if not manifest.get('selected_direction') or concept.get('selected_direction') != manifest['selected_direction']:
        raise ValueError('Production direction differs from the concept selection')
    gates = RUN_SCOPE_GATES['concept-only']
    if track == 'marketing-plan':
        # AI declares the actual work stage; prose, filenames and page count do
        # not decide whether the request makes samples or the full deck.
        stage = request.get('marketing_stage')
        if stage not in {'sample', 'full-deck'}:
            raise ValueError('Marketing production needs an explicit sample/full-deck marketing_stage')
        if request.get('production_stage', 'artwork') != 'artwork':
            raise ValueError('Print prototype stages cannot replace marketing_stage')
        if stage == 'full-deck':
            gates = RUN_SCOPE_GATES['production-candidate']
            results = load(inside(root, artifacts.get('quality_gate_results')))
            samples = [r for r in results.get('results', [])
                       if r.get('gate_id') == 'marketing-plan.five-page-content']
            if len(samples) != 1 or samples[0].get('status') != 'pass' or samples[0].get('boundaries'):
                raise ValueError('Full deck needs the five-page review passed with its conditions resolved')
    checks = validate_quality_gate_results(root, inside(root, artifacts.get('quality_gate_results')),
        track, manifest.get('run_id'), gates, prerequisite_only=True)
    if track == 'marketing-plan':
        from visual_generation_capability_contract import validate_visual_generation_capability
        checks += validate_visual_generation_capability(manifest, manifest['run_scope'], root)
    failed = [c['name'] for c in checks if not c['passed']]
    if failed:
        raise ValueError('Track production prerequisites failed: ' + ', '.join(failed))
    return checks
