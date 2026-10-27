"""Bind a selected direction and its visual notes to a prototype request and observation.

This prepares inputs; it neither calls an image tool nor certifies host provenance,
visual quality, production authorization or user approval.
"""
import argparse
import json
from pathlib import Path

from review_contract import bound_file, inside, load
from review_workflow import allocate, write, error


def _direction(root, manifest_ref):
    from validate_print_ad_run import validate_direction_blind_review, load_claim_lock
    manifest = load(bound_file(root, manifest_ref))
    result = validate_direction_blind_review(root, manifest)
    if not result['passed']:
        error('manifest.direction_adoption', result['evidence'], 'existing complete direction and actual selection check')
    lock = load_claim_lock(root, manifest['direction_adoption'])
    return manifest, lock, result['evidence']


def _references(root, references):
    if not isinstance(references, list):
        error('references', references, 'a list of role/file references; an empty list is allowed')
    for item in references:
        if not isinstance(item, dict) or set(item) != {'role', 'file'} or not isinstance(item['role'], str) or not item['role'].strip():
            error('references', item, 'a concrete reference role and a bound file')
        bound_file(root, item['file'])
    return references


def _prompt(lock, visual_text, shared, scene_prompt, references):
    if not isinstance(scene_prompt, str) or not scene_prompt.strip():
        error('scene_prompt', scene_prompt, 'the actual scene and composition requirements')
    return ('选定方向：' + lock['direction_id'] + '\n锁定创意原句：\n' + lock['statement']
            + '\n已展示并选定的视觉要求：\n' + visual_text
            + ('\n系列共同美术：\n' + shared if shared else '')
            + '\n本稿场景与构图：\n' + scene_prompt
            + '\n参考输入及职责：\n' + json.dumps(references, ensure_ascii=False, indent=2) + '\n')


def _inputs(root, manifest_ref, visual_direction, scene_prompt, references):
    manifest, lock, evidence = _direction(root, manifest_ref)
    visual_text = bound_file(root, visual_direction).read_text(encoding='utf-8')
    if not visual_text.strip():
        error('visual_direction', visual_direction, 'the selected direction visual notes, not an empty style label')
    from user_decision_contract import effective_series_plan
    plan = effective_series_plan(root, manifest)
    shared = plan.get('shared_art_direction', '')
    if not isinstance(shared, str):
        error('series_plan.shared_art_direction', shared, 'the existing common art direction string')
    if manifest.get('series_mode') == 'series' and not shared.strip():
        error('series_plan.shared_art_direction', shared, 'the selected series common art direction')
    _references(root, references)
    return lock, evidence, shared, _prompt(lock, visual_text, shared, scene_prompt, references)


def prepare(root, manifest, visual_direction, scene_prompt, references):
    """Use the saved selected visual note; do not add it to the anonymous rubric."""
    lock, evidence, shared, prompt = _inputs(root, manifest, visual_direction, scene_prompt, references)
    path = allocate(root, 'prototype-input')
    prompt_ref = write(root, path / 'prompt.txt', prompt, raw=True)
    state = dict(kind='selected-prototype-input-v1', manifest=manifest, visual_direction=visual_direction,
                 direction=lock, direction_check=evidence, shared_art_direction=shared,
                 scene_prompt=scene_prompt, references=references, prompt=prompt_ref)
    prepared = write(root, path / 'prepared.json', state)
    return dict(prepared=prepared, prompt=prompt_ref, inputs=references,
                next_action='Submit this exact prompt and the listed reference roles through the actual image tool.')


def _prepared(root, prepared):
    state = load(bound_file(root, prepared))
    if state.get('kind') != 'selected-prototype-input-v1':
        error('prepared.kind', state.get('kind'), 'prepare output')
    lock, evidence, shared, prompt = _inputs(root, state['manifest'], state['visual_direction'], state['scene_prompt'], state['references'])
    if lock != state['direction'] or evidence != state['direction_check'] or shared != state['shared_art_direction']:
        error('prepared.direction', state['direction'], 'unchanged checked direction and selected visual notes')
    if bound_file(root, state['prompt']).read_text(encoding='utf-8') != prompt:
        error('prepared.prompt', state['prompt'], 'the exact composed prompt from the checked inputs')
    return state, prompt


def observe(root, prepared, actual_request, artifact, observation, style_matches):
    """Record a real view of the returned image, against the same submitted inputs."""
    state, prompt = _prepared(root, prepared)
    request = load(bound_file(root, actual_request))
    if request.get('prompt') != prompt or request.get('references') != state['references']:
        error('actual_request', actual_request, 'the exact submitted prompt and reference roles from prepare')
    _references(root, request['references'])
    from visual_review_contract import image_file
    image_file(root, artifact)
    if type(style_matches) is not bool or not isinstance(observation, str) or not observation.strip():
        error('style_observation', observation, 'a concrete observation after viewing the actual image and a boolean style comparison')
    path = allocate(root, 'prototype-observation')
    status = 'style-observed' if style_matches else 'needs-correction'
    record = dict(kind='selected-prototype-observation-v1', prepared=prepared, actual_request=actual_request,
                  artifact=artifact, direction_id=state['direction']['direction_id'],
                  visual_direction=state['visual_direction'], style_matches=style_matches, observation=observation,
                  status=status, content_pass_granted=False,
                  host_provenance_certified=False)
    return dict(observation=write(root, path / 'observation.json', record), status=status,
                content_pass_granted=False,
                next_action='Continue the existing representative prototype content review; this observation grants no series permission.' if style_matches else 'Correct the observed style deviation before extending the series.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--action', choices=['prepare', 'observe'], required=True)
    parser.add_argument('--payload', required=True)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    try:
        payload = load(inside(root, args.payload))
        result = prepare(root, **payload) if args.action == 'prepare' else observe(root, **payload)
        print(json.dumps(dict(status='ok', result=result), ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps(dict(status='failed', reason=str(exc)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
