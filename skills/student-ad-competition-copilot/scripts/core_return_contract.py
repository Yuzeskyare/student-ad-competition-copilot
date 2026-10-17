"""Immutable invalid-return registration; never discard an adverse valid verdict."""
import copy
import json
from datetime import datetime, timezone
from review_contract import bound_file, load, timestamp

LIMIT = 2


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate_return(root, manifest, row, *, prefix_only=False, contract_only=False):
    from validate_print_ad_run import validate_blind_core, load_claim_lock
    record = load(bound_file(root, row['independent_check']))
    render = load(bound_file(root, row['render_record']))
    adoptions = manifest['direction_adoption'].get('previous_adoptions', []) + [manifest['direction_adoption']]
    locks = [load_claim_lock(root, a) for a in adoptions]
    lock = next((a for a in locks if a['direction_id'] == row['direction_id'] and a['statement_sha256'] == row['core_claim_sha256']), None)
    require(lock is not None, 'Invalid-return registration needs the original adopted claim lock')
    bound_file(root, record['raw_return'])
    validate_blind_core(root, row, render, record, set(), lock, validate_return=not prefix_only, return_contract_only=contract_only)
    return record


def return_error(root, manifest, row):
    # File/input/identity/rubric/timing failures are not return violations.
    record = validate_return(root, manifest, row, prefix_only=True)
    try:
        raw = json.loads(bound_file(root, record['raw_return']).read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError:
        raw = None
    if isinstance(raw,dict) and 'answers' in raw:
        require(raw['answers'] == row['answers'], 'Preserve original independent answers before invalidating a return')
    try:
        validate_return(root, manifest, row, contract_only=True)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        return str(exc)
    raise ValueError('Valid independent return cannot be invalidated for an adverse conclusion')


def review_state(root, manifest, *, allow_pending=False):
    review = manifest.get('core_creative_review', {})
    from user_decision_contract import terminal_rejections
    rejected = terminal_rejections(root, manifest) if manifest.get('review_contract') else {}
    rejected_hashes={k[1] for k in rejected}
    rejected_rows = [r for r in review.get('assessments',[]) if rejected_hashes and (r['observed_image']['sha256'] in rejected_hashes or r['artifact']['sha256'] in rejected_hashes)]
    rejected_renders=[]
    for ref in review.get('completed_draft_render_records',[]) if rejected_hashes else []:
        render=load(bound_file(root,ref))
        if render['source']['sha256'] in rejected_hashes or any(v['file']['sha256'] in rejected_hashes for v in render['views'] if v['scale']=='native'):
            rejected_renders.append(ref)
    if rejected_rows or rejected_renders:
        # Preserve all evidence bytes and answers. This projection records a
        # user rejection, not an invalidation, replacement, or successful review.
        for row in rejected_rows:
            bound_file(root,row['artifact']);bound_file(root,row['observed_image'])
            rec=load(bound_file(root,row['independent_check']))
            bound_file(root,rec['raw_return'])
            decision=next(r for k,r in rejected.items() if k[1] in {row['observed_image']['sha256'],row['artifact']['sha256']})
            render=load(bound_file(root,row['render_record']))
            from review_contract import artifact
            require(artifact(root,render['source'])==artifact(root,row['artifact']) and any(v['file']==row['observed_image'] for v in render['views'] if v['scale']=='native'), 'Rejected assessment must bind its actual original render')
            require(timestamp(render['created_at'])<=timestamp(decision['decided_at']), 'User rejection must follow the viewed render')
        ids={r['id'] for r in rejected_rows}
        render_refs=rejected_renders+[r['render_record'] for r in rejected_rows]
        retained=dict(review,assessments=[r for r in review['assessments'] if r['id'] not in ids],
                      current_assessment_ids=[i for i in review.get('current_assessment_ids',[]) if i not in ids],
                      completed_draft_render_records=[r for r in review.get('completed_draft_render_records',[]) if r not in render_refs],
                      invalid_returns=[e for e in review.get('invalid_returns',[]) if e['assessment_id'] not in ids])
        result=review_state(root,dict(manifest,core_creative_review=retained),allow_pending=allow_pending)
        result['terminal_rejection_audit']=[dict(r,retained_assessment_ids=[x['id'] for x in rejected_rows if x['artifact']['sha256']==r['artwork']['sha256'] or x['observed_image']['sha256']==r['artwork']['sha256']],retained_returns=[load(bound_file(root,x['independent_check']))['raw_return'] for x in rejected_rows if r['artwork']['sha256'] in {x['artifact']['sha256'],x['observed_image']['sha256']}],content_pass_granted=False) for r in rejected.values()]
        return result
    entries = review.get('invalid_returns', [])
    if not entries:
        return copy.deepcopy(review)
    require(isinstance(entries, list), 'invalid_returns must be a list')
    rows = review['assessments']
    by_id = {r['id']: r for r in rows}
    require(len(by_id) == len(rows), 'Core assessment IDs must be unique')
    invalid = set(); replacements = set(); counts = {}; audits = []
    for entry in entries:
        require(set(entry) == {'assessment_id','raw_return','validator_error','registered_at','replacement_assessment_id'}, 'Invalid core return registration fields')
        ident = entry['assessment_id']
        require(ident in by_id and ident not in invalid, 'Invalid return must identify one retained assessment')
        row = by_id[ident]
        record = validate_return(root, manifest, row, prefix_only=True)
        require(entry['raw_return'] == record['raw_return'], 'Invalid return must bind original raw file SHA256')
        error = return_error(root, manifest, row)
        require(entry['validator_error'] == error, 'Invalid return validator error differs from actual error')
        at = timestamp(entry['registered_at'])
        require(timestamp(row['checked_at']) <= at <= datetime.now(timezone.utc), 'Invalid registration must follow the original return')
        key = row['observed_image']['sha256']
        counts[key] = counts.get(key, 0) + 1
        require(counts[key] <= LIMIT, 'Invalid return replacement limit exceeded; stop for user decision')
        invalid.add(ident)
        successor = entry['replacement_assessment_id']
        if successor is None:
            require(allow_pending, 'Invalid core return awaits a new independent replacement')
        else:
            require(successor in by_id and successor not in replacements and successor != ident, 'Replacement must identify a new retained assessment')
            new = by_id[successor]
            # Decisions and rework belong to their original evidence, never copied.
            excluded = {'id','answers','independent_check','checked_at','rework','user_confirmations','product_triptychs'}
            require({k:v for k,v in row.items() if k not in excluded} == {k:v for k,v in new.items() if k not in excluded}, 'Replacement must review the same artwork SHA256 and original inputs')
            require('user_confirmations' not in new, 'Replacement cannot inherit confirmations of another return')
            require([(p['element_id'],p['role']) for p in row.get('product_triptychs',[])] == [(p['element_id'],p['role']) for p in new.get('product_triptychs',[])], 'Replacement must retain the same product evidence scope')
            rec = validate_return(root, manifest, new, prefix_only=True)
            blind = load(bound_file(root, rec['blind_read']))
            require(at < timestamp(blind['input_prepared_at']), 'Replacement must start a new blind read after invalid registration')
            for candidate in rows:
                if candidate['id'] == successor or timestamp(candidate['checked_at']) > timestamp(new['checked_at']):
                    continue
                old = load(bound_file(root, candidate['independent_check']))
                old_blind = load(bound_file(root, old['blind_read']))
                for phase in (blind, rec):
                    require(phase.get('checker_session_id') and phase.get('invocation_id'), 'Replacement needs observable new checker session and invocation identifiers')
                    require(all(phase['checker_session_id'] != p.get('checker_session_id') and phase['invocation_id'] != p.get('invocation_id') for p in (old,old_blind)), 'Replacement must use new empty-context independent sessions and invocations')
            replacements.add(successor)
        audits.append(dict(kind='invalid-core-return', **entry, artwork_sha256=key))
    active = [r for r in rows if r['id'] not in invalid]
    if not allow_pending:
        for row in active:
            # Validate every returned contract before folding. A replacement
            # additionally needs the full input/pixel check. Historical input
            # evidence keeps its existing unified-review checks; input failures
            # must not become grounds for discarding a valid historical verdict.
            validate_return(root, manifest, row, contract_only=row['id'] not in replacements)
    # One effective latest return for each exact artwork; unrelated history stays.
    latest = {}
    for row in active:
        key = (row['artifact']['path'],row['artifact']['sha256'],tuple(row['artifact'].get('units', [])))
        if key not in latest or timestamp(row['checked_at']) > timestamp(latest[key]['checked_at']):
            latest[key] = row
    active_ids = {r['id'] for r in latest.values()}
    current = []
    links = {e['assessment_id']:e['replacement_assessment_id'] for e in entries}
    for ident in review.get('current_assessment_ids', []):
        visited = set()
        while ident in links:
            require(ident not in visited, 'Invalid return replacement cycle')
            visited.add(ident); ident = links[ident]
        if ident is not None:
            require(ident in active_ids, 'Current assessment hides a newer independent return')
            current.append(ident)
    result = dict(review, assessments=[r for r in active if r['id'] in active_ids], current_assessment_ids=current)
    result['invalid_return_audit'] = audits
    return result


def update_review(root, manifest, action, payload):
    review = copy.deepcopy(manifest['core_creative_review'])
    review_state(root, manifest, allow_pending=True)
    rows = {r['id']:r for r in review['assessments']}
    if action == 'invalidate-core-return':
        require(set(payload) == {'assessment_id','validator_error'}, 'Invalidation payload needs assessment_id and exact validator_error')
        ident = payload['assessment_id']
        require(ident in rows, 'Unknown retained assessment')
        entries = review.setdefault('invalid_returns', [])
        require(not any(e['assessment_id'] == ident for e in entries), 'Return already invalidated')
        # Only the latest attached return for this image may be invalidated.
        effective = review_state(root, manifest, allow_pending=True)
        require(ident in {r['id'] for r in effective['assessments']}, 'Only the latest retained return may be invalidated')
        error = return_error(root, manifest, rows[ident])
        require(payload['validator_error'] == error, 'Invalid return validator error differs from actual error')
        rec = load(bound_file(root, rows[ident]['independent_check']))
        entries.append(dict(assessment_id=ident,raw_return=rec['raw_return'],validator_error=error,registered_at=datetime.now(timezone.utc).isoformat(),replacement_assessment_id=None))
    else:
        require(set(payload) == {'assessment_id','replacement'}, 'Replacement payload needs assessment_id and replacement assessment')
        matches = [e for e in review.get('invalid_returns', []) if e['assessment_id'] == payload['assessment_id'] and e['replacement_assessment_id'] is None]
        require(len(matches) == 1, 'Replacement needs one pending invalid return')
        new = payload['replacement']
        require(new['id'] not in rows, 'Replacement assessment ID must be new')
        review['assessments'].append(copy.deepcopy(new))
        matches[0]['replacement_assessment_id'] = new['id']
    candidate = dict(manifest, core_creative_review=review)
    # Attaching a malformed return keeps it visible and blocked by the normal
    # validator until its own real error is registered; retries cannot disappear.
    review_state(root, candidate, allow_pending=True)
    return review
