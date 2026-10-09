"""Current artifact source checks shared by delivery and selection helpers."""
import xml.etree.ElementTree as ET
from execution_contract import PROFILE, require
from review_contract import bound_file, inside, load, artifact, timestamp
from inspect_svg_source import inspect


def scene_provenance(root, scene):
    provenance = load(bound_file(root, scene.get('provenance')))
    require(provenance.get('output') == scene['file'], 'Main scene differs from its returned output binding')
    profile = provenance.get('profile', 'host-call-v1')
    if profile == 'host-call-v1':
        require(provenance.get('call_id') == scene.get('call_id') and bool(scene.get('call_id')),
                'Main scene must match actual call output evidence')
    elif profile == 'tool-output-observation-v1':
        from datetime import datetime, timezone
        require(isinstance(provenance.get('tool_name'), str) and provenance['tool_name'].strip(),
                'Tool output observation needs the actual tool name')
        load(bound_file(root, provenance.get('parameters')))
        raw_return = bound_file(root, provenance.get('raw_return')).read_text(encoding='utf-8-sig')
        require(raw_return.strip(), 'Tool output observation needs its nonempty raw return')
        require(timestamp(provenance.get('observed_at')) <= datetime.now(timezone.utc),
                'Output observation must use its actual local observation time')
        require(provenance.get('call_id') is None and scene.get('call_id') is None,
                'Use host-call-v1 for exposed call IDs; never substitute a file ID')
        limits = provenance.get('unavailable_metadata', {})
        require(isinstance(limits, dict) and all(isinstance(limits.get(k), str) and limits[k].strip()
                for k in ('call_id', 'host_event_time')), 'Explain unavailable host ID and event time')
        file_id = provenance.get('output_file_id')
        reason = provenance.get('output_file_id_unavailable_reason')
        require((isinstance(file_id, str) and file_id.strip() and file_id in raw_return)
                or (file_id is None and isinstance(reason, str) and reason.strip()),
                'Bind the exposed output file ID or explain why it is unavailable')
    else:
        raise ValueError('Unknown scene provenance profile')
    return profile


def required(manifest, contract, root):
    return (manifest.get('execution_profile') == PROFILE or
            any(load(bound_file(root, r)).get('execution_profile') == PROFILE
                for r in contract['production_requests']))


def validate_current(root, manifest, contract):
    if manifest.get('category') != 'print-ad' or not required(manifest, contract, root):
        return []
    require(bool(contract['final_artifacts']), 'Current artwork set is empty')
    results = []
    members = []
    for ref in contract['final_artifacts']:
        artifact(root, ref)
        require(len(ref['units']) == 1, 'Each current print member must identify one artwork, not a format copy')
        members.extend(ref['units'])
        bundle = ref.get('current_source')
        require(isinstance(bundle, dict), 'Current print artwork needs current_source relationships')
        native = bound_file(root, bundle.get('native'))
        bound_file(root, bundle.get('preview'))
        purpose = bundle.get('purpose')
        require(purpose in {'creative-master', 'submission-version'}, 'Declare artwork purpose')
        if purpose == 'submission-version':
            evidence = load(bound_file(root, bundle.get('purpose_authorization')))
            require(evidence.get('actor_type') == 'human' and bundle.get('purpose_quote') and
                    bundle['purpose_quote'] in evidence.get('text', ''), 'Submission version needs existing explicit user scope')
        render = load(bound_file(root, bundle.get('render_record')))
        require(render.get('source') == bundle['native'], 'Render record belongs to a different native source')
        bound_file(root, render.get('execution_evidence'))
        view = bound_file(root, render.get('render'))
        from PIL import Image
        for image_path in (bound_file(root, ref), bound_file(root, bundle['preview']), view):
            with Image.open(image_path) as image:
                image.verify()
        require(render.get('compared_artifact') == {k: ref[k] for k in ('path', 'sha256', 'version', 'units')},
                'Source render was not compared to the current artwork')
        require(render.get('correspondence') == 'matched' and render.get('observation'), 'Inspect actual rendered correspondence')
        review = bundle.get('process_review', {})
        require(review.get('render') == render['render'] and review.get('status') == 'clear' and review.get('observation'),
                'Inspect process labels on the actual current source render')
        scene = bundle.get('scene')
        provenance_profile = None
        if scene:
            bound_file(root, scene.get('file'))
            provenance_profile = scene_provenance(root, scene)
        else:
            require(bundle.get('no_scene_reason'), 'Identify main scene or explain why no raster scene applies')
        scan = None
        if native.suffix.lower() == '.svg':
            dep = bundle.get('dependency_root')
            dependency_root = root if dep == '.' else inside(root, dep)
            try:
                scan = inspect(native, dependency_root, scene.get('node_id') if scene else None,
                               scene['file']['sha256'] if scene else None)
            except ET.ParseError as exc:
                raise ValueError('Invalid SVG source: '+str(exc)) from exc
            require(scan['status'] != 'failed', '; '.join(scan['errors']))
            if scene:
                require(scan['scene_binding'] == 'matched', 'SVG main scene has not been checked')
            candidates = scan['process_label_candidates']
            if purpose == 'creative-master' and candidates:
                dispositions = review.get('candidate_dispositions', [])
                require(len(dispositions) == len(candidates), 'Unresolved process-label candidates in creative master')
                for text, item in zip(candidates, dispositions):
                    require(item.get('text') == text and item.get('classification') in {'not-visible', 'non-production-copy'}
                            and item.get('reason'), 'Visible production labels must be repaired, not accepted as required disclosure')
        else:
            require(bundle.get('native_inspection') and bundle['native_inspection'].get('observation'),
                    'Non-SVG native sources require an applicable inspection record')
            bound_file(root, bundle['native_inspection'].get('evidence'))
        results.append(dict(unit=ref['units'][0], native=str(native), render=str(view), svg_scan=scan,
                            scene_provenance_profile=provenance_profile,
                            host_lifecycle_certified=False,
                            scope='structural-and-source-binding', visual_quality_certified=False))
    require(len(set(members)) == len(members), 'Duplicate current member; format copies are not new members')
    plan = manifest.get('series_plan', {})
    require(set(members) == set(plan.get('units', [])), 'Current members differ from the effective series plan')
    roles = plan.get('member_roles', [])
    require(len(roles) == len(members) and {r.get('unit') for r in roles} == set(members),
            'Record each member role; previews and format copies cannot fill the plan')
    require(all(r.get('benefit_or_action') and r.get('contribution') for r in roles),
            'Each member needs its actual benefit/action and contribution, not only a count')
    require(plan.get('shared_art_direction') and plan.get('scope_basis'), 'Preserve effective scope basis and common art direction')
    for basis in plan['scope_basis']:
        bound_file(root, basis)
    return results
