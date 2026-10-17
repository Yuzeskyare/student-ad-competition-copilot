"""Explicit human direction changes; immutable history, ordinary independent checks."""
import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def inherited_model_redivergences(root, adoption, event_ids=None):
    """Count earlier bundles across user changes, including intervening model locks."""
    from validate_print_ad_run import bound_file, load_json
    event_ids = set() if event_ids is None else event_ids
    cursor = adoption
    while 'user_direction_change' not in cursor:
        history = cursor.get('previous_adoptions', [])
        if not history:
            return 0
        cursor = history[-1]
    event = load_json(bound_file(root, cursor['user_direction_change']))
    source = load_json(bound_file(root, event['source']))
    if source['event_id'] in event_ids:
        raise ValueError('A user direction-change event cannot be reused')
    event_ids.add(source['event_id'])
    previous = load_json(bound_file(root, event['previous_manifest']))['direction_adoption']
    bundle = load_json(bound_file(root, previous['blind_review']))
    return len(bundle['rounds']) - 1 + inherited_model_redivergences(root, previous, event_ids)


def validate_change(root, manifest):
    from review_contract import human_source, timestamp
    from validate_print_ad_run import bound_file, load_json, load_claim_lock, validate_direction_blind_review
    adoption = manifest['direction_adoption']
    event = load_json(bound_file(root, adoption['user_direction_change']))
    fields = {'kind', 'action', 'source', 'quote', 'decided_at', 'previous_manifest'}
    if (set(event) != fields or event['kind'] != 'user-direction-change'
            or event['action'] not in {'rediverge', 'change-direction', 'amend-statement', 'provided-direction'}):
        raise ValueError('Explicit user direction-change decision fields are required')
    at = human_source(root, event['source'], event['quote'])
    explicit = re.search(r'重新|改|换|新.{0,6}(方向|思路|方案)|方向|画面|用.{1,40}(表现|表达|代替)|rediverg|brainstorm|change|revise|switch|new direction|use this|draw|depict', event['quote'], re.I)
    # A supplied visual sentence need not contain the verb "change". Its actual
    # source remains bound and the sentence still receives the ordinary check.
    provided = event['action'] == 'provided-direction'
    generic = re.fullmatch(r'\s*(继续(?:做|推进)?|做完|完成|好的?|可以|确认|同意|ok|yes|continue|go ahead)[\s。！.!]*', event['quote'], re.I)
    if generic or (not explicit and not provided):
        raise ValueError('A generic continue/delegation message is not an explicit direction-change request')
    source = load_json(bound_file(root, event['source']))
    if (source['kind'] != 'user-message' or at != timestamp(event['decided_at'])
            or at > datetime.now(timezone.utc)):
        raise ValueError('Direction-change time must match the original user message')
    # When a host transcript is available, validate the actual user message too.
    if 'host_event' in source:
        host = load_json(bound_file(root, source['host_event']))
        message = host.get('message', host).get('payload', {})
        contents = message.get('content', [])
        if (message.get('role') != 'user' or not any(event['quote'] in x.get('text', '') for x in contents)):
            raise ValueError('Direction-change quotation differs from the bound host user message')
    previous = load_json(bound_file(root, event['previous_manifest']))
    for key in ('run_id', 'competition', 'category', 'creative_contract', 'direction_contract'):
        if previous.get(key) != manifest.get(key):
            raise ValueError('User direction change must remain in the same run and contracts')
    old = previous['direction_adoption']
    if not validate_direction_blind_review(root, previous)['passed']:
        raise ValueError('Previous direction adoption must remain valid and traceable')
    if not timestamp(old['adopted_at']) <= at < timestamp(adoption['adopted_at']):
        raise ValueError('User change must follow the old adoption and precede the new lock')
    if adoption.get('previous_adoptions') != old.get('previous_adoptions', []) + [old]:
        raise ValueError('User direction change must preserve every previous adoption unchanged')
    if adoption['selection_mode'] != 'user':
        raise ValueError('User direction change requires confirmation after independent checking')
    selection = load_json(bound_file(root, adoption['selection_record']))
    if human_source(root, selection['source'], selection['statement']) != timestamp(selection['decided_at']):
        raise ValueError('New direction confirmation must bind its original user message time')
    bundle = load_json(bound_file(root, adoption['blind_review']))
    first = load_json(bound_file(root, bundle['rounds'][0]))
    if not at < timestamp(first['input_prepared_at']):
        raise ValueError('New independent direction check must follow the user change')
    if adoption['blind_review'] == old['blind_review'] or adoption['claim_lock'] == old['claim_lock']:
        raise ValueError('User direction change needs a new independent check and claim lock')
    load_claim_lock(root, old)
    # Preserve old drafts and all review rows, including invalid-return history.
    for key in ('assessments', 'completed_draft_render_records', 'invalid_returns'):
        values = previous.get('core_creative_review', {}).get(key, [])
        current = manifest.get('core_creative_review', {}).get(key)
        if values and (not isinstance(current, list) or current[:len(values)] != values):
            raise ValueError('User direction change must preserve all old drafts and reviews')
    used = inherited_model_redivergences(root, adoption)
    from direction_redivergence_contract import limit
    if used + len(bundle['rounds']) - 1 > limit(manifest):
        raise ValueError('Model-initiated re-divergence limit is exhausted; a new explicit user decision is required')
    supplied = event['action'] in {'amend-statement', 'provided-direction'}
    if supplied and adoption['method_retrieval'] != old['method_retrieval']:
        raise ValueError('User-supplied direction reuses the original method evidence unchanged')
    return dict(supplied=supplied, model_redivergences_used=used, event=event)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir', 'previous-manifest', 'adoption', 'decision', 'output'):
        p.add_argument('--'+name, required=True)
    from direction_redivergence_contract import CONTRACT
    p.add_argument('--redivergence-contract', choices=[CONTRACT])
    args = p.parse_args()
    from review_contract import inside, digest
    from validate_print_ad_run import load_json, validate_direction_blind_review
    root = Path(args.run_dir).resolve()
    target = inside(root, args.output)
    if target.exists():
        raise ValueError('Preserve existing snapshots; choose a new output path')
    previous_path = inside(root, args.previous_manifest)
    previous = load_json(previous_path)
    event_path = inside(root, args.decision)
    event = load_json(event_path)
    if event['previous_manifest'] != dict(path=args.previous_manifest, sha256=digest(previous_path)):
        raise ValueError('Decision must bind the exact previous manifest')
    current = copy.deepcopy(previous)
    if args.redivergence_contract:
        current['direction_redivergence_contract'] = args.redivergence_contract
    adoption = load_json(inside(root, args.adoption))
    adoption['previous_adoptions'] = previous['direction_adoption'].get('previous_adoptions', []) + [previous['direction_adoption']]
    adoption['user_direction_change'] = dict(path=args.decision, sha256=digest(event_path))
    current.update(selected_direction=adoption['direction_id'], direction_adoption=adoption)
    result = validate_direction_blind_review(root, current)
    if not result['passed']:
        raise ValueError(result['evidence'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
