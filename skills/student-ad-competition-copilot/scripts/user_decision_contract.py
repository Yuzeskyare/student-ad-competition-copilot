"""Exact-artwork human confirmations and explicitly selected delivery scope.

These records change the effective decision, never the independent raw return.
Meaning is supplied by independent AI classification, never inferred from words.
Historical returns remain unchanged; a bound current classification can supplement them.
"""
from datetime import datetime, timezone
from review_contract import artifact, bound_file, human_source, load, timestamp


def require(value, message):
    if not value:
        raise ValueError(message)


def terminal_rejections(root, manifest):
    """A retained final/reject is terminal for these exact pixels, never a pass."""
    from review_contract import read_contract, coverage
    contract, rows = read_contract(root, manifest)
    rejected = {}
    for decision in rows.values():
        if decision['stage'] != 'final' or decision['decision'] != 'reject':
            continue
        for ref in decision['reviewed_artifacts']:
            artifact(root, ref)
            key = (ref['path'], ref['sha256'])
            rejected[key] = dict(decision_id=decision['id'], source=decision['source'],
                                 quote=decision['quote'], decided_at=decision['checked_at'], artwork=ref)
    if manifest.get('run_scope') == 'delivery-candidate':
        require(not any(r['sha256'] in {k[1] for k in rejected} for r in contract.get('final_artifacts',[])),
                'Terminally user-rejected artwork cannot pass or be delivered')
    return rejected


QUESTIONS = {'label_consistent_readable', 'product_label_consistent_readable', 'layout_readable'}
BASES = {'subjective-uncertainty', 'verified-error'}


def validate_judgment_fields(raw):
    if 'judgment_basis' in raw:
        bases = raw['judgment_basis']
        require(isinstance(bases, dict) and set(bases) <= QUESTIONS
                and all(isinstance(v, str) and v in BASES for v in bases.values()),
                'Independent judgment_basis must map supported questions to existing judgment categories')
        for question in bases:
            answer = raw.get('answers', {}).get(question)
            value = answer.get('answer') if isinstance(answer, dict) else raw.get(question)
            require(value is False, 'A judgment category must describe an existing false answer, not contradict or invent one')
    if 'verified_errors' in raw:
        require(isinstance(raw['verified_errors'], list)
                and all(isinstance(v, str) and v.strip() for v in raw['verified_errors']),
                'verified_errors must be an explicit list of independently observed errors')
        require(not raw['verified_errors'] or 'verified-error' in raw.get('judgment_basis', {}).values(),
                'Explicit verified errors must bind an existing false answer classified as verified-error')


def subjective_doubt(raw, question, observation=None):
    validate_judgment_fields(raw)
    if raw.get('meaning_check', {}).get('reversed') or raw.get('compliance_check', {}).get('violated'):
        return False
    if raw.get('verified_errors'):
        return False
    checks = raw.get('comparison', {}).get('product_label', {}).get('checks', [])
    if any(any(row.get(k) is True for k in ('mirrored', 'inverted', 'misspelled', 'pseudo_text')) for row in checks):
        return False
    return raw.get('judgment_basis', {}).get(question) == 'subjective-uncertainty'


def classified_return(root, decision, raw_ref, raw, question, observation, completed_at, original_author=None):
    """Supplement missing historical classification, never rewrite an existing verdict."""
    validate_judgment_fields(raw)
    ref = decision.get('judgment_classification')
    if ref is None:
        require(question in raw.get('judgment_basis', {}),
                'Missing independent judgment category: classify the saved return now; preserve history and existing user confirmation')
        return raw
    classification = load(bound_file(root, ref))
    fields = {'kind', 'independent_raw', 'question', 'observation', 'judgment_basis',
              'checker_context', 'author_session_id', 'checker_session_id', 'invocation_id', 'completed_at'}
    require(set(classification) == fields and classification['kind'] == 'independent-judgment-classification'
            and classification['independent_raw'] == raw_ref and classification['question'] == question
            and classification['observation'] == observation,
            'Current classification must bind the exact original return, question and observation')
    require(question not in raw.get('judgment_basis', {}) and classification['judgment_basis'] in BASES,
            'Do not replace an existing independent category with a new classification')
    require(classification['checker_context'] == 'fresh-isolated'
            and all(isinstance(classification[k], str) and classification[k].strip()
                    for k in ('author_session_id', 'checker_session_id', 'invocation_id'))
            and classification['author_session_id'] != classification['checker_session_id'],
            'Historical classification requires a separate independent AI pass')
    require(isinstance(original_author, str) and bool(original_author.strip())
            and classification['author_session_id'] == original_author
            and classification['checker_session_id'] != original_author,
            'Classification must preserve the known original author and exclude that author as checker')
    require(timestamp(completed_at) <= timestamp(classification['completed_at']) <= datetime.now(timezone.utc),
            'Classification must use its actual current time, never backdate history')
    return dict(raw, judgment_basis={**raw.get('judgment_basis', {}), question: classification['judgment_basis']})


def confirmations(root, holder, raw_ref, raw, current, completed_at, original_author=None):
    """Validate every supplied record, including unused/stale confirmations."""
    confirmed = {}
    for ref in holder.get('user_confirmations', []):
        decision = load(bound_file(root, ref))
        q = decision.get('question')
        require(q in {'label_consistent_readable', 'product_label_consistent_readable', 'layout_readable'},
                'Human confirmation cannot override compliance, reversal or visible scene conflicts')
        answer = raw.get('answers', {}).get(q)
        value = answer['answer'] if answer else raw.get(q)
        observation = answer['observation'] if answer else raw.get('label_observation')
        classified = classified_return(root, decision, raw_ref, raw, q, observation, completed_at, original_author)
        require(value is False and subjective_doubt(classified, q),
                'Only an independent subjective uncertainty may receive human confirmation; verified errors require repair')
        require(q not in confirmed and decision.get('kind') == 'exact-artwork-confirmation'
                and decision.get('decision') == 'confirm' and decision.get('independent_raw') == raw_ref
                and decision.get('observation') == observation,
                'Confirmation must preserve the exact independent return and observation')
        reviewed = decision.get('reviewed_artifact')
        artifact(root, reviewed)
        require(all(reviewed.get(k) == current.get(k) for k in ('path', 'sha256')),
                'Human confirmation uses stale artwork pixels')
        at = human_source(root, decision.get('source'), decision.get('quote'))
        source = load(bound_file(root, decision['source']))
        seen = source.get('reviewed_artifact', {})
        require((seen.get('path') == current['path'] and seen.get('sha256') == current['sha256'])
                or current['path'] in source['text'] or current['sha256'] in source['text'],
                'Human source must identify the exact viewed artwork')
        require(timestamp(completed_at) <= at == timestamp(decision.get('decided_at')) <= datetime.now(timezone.utc),
                'Confirmation must follow the independent check and preserve actual human event time')
        confirmed[q] = dict(decision=ref, question=q, independent_raw=raw_ref,
                            independent_answer=False, observation=observation,
                            effective_decision='human-confirmed', source=decision['source'],
                            quote=decision['quote'], decided_at=decision['decided_at'], reviewed_artifact=reviewed)
    return confirmed


def assessment_confirmations(root, row, record=None, raw=None):
    if not row.get('user_confirmations'):
        return {}
    record = record or load(bound_file(root, row['independent_check']))
    raw = raw or load(bound_file(root, record['raw_return']))
    # Humans view the native render; the editable source may be SVG/PSD.
    current = row.get('observed_image', row['artifact'])
    return confirmations(root, row, record['raw_return'], raw, current, record['completed_at'], record.get('author_session_id'))


def effective_series_plan(root, manifest):
    from series_commit import validate_commit
    validate_commit(root,manifest)
    plan = manifest.get('series_plan', {})
    binding = manifest.get('series_direction_batch')
    if binding is not None:
        from workflow_runtime import semantics
        batch = load(bound_file(root, binding['batch']))
        require(batch.get('kind') in {'series-direction-batch-v1','series-direction-batch-v2'}
                and semantics(plan) == batch['plan'] and manifest.get('series_mode') == plan.get('mode')
                and binding['unit'] in plan['units'], 'Member plan differs from its presented series batch')
        members = [m for m in batch['members'] if m['unit'] == binding['unit']]
        require(len(members) == 1 and manifest.get('selected_direction') == members[0]['direction_id'],
                'Member direction differs from its checked series batch')
        selection = load(bound_file(root, manifest['direction_adoption']['selection_record']))
        source = load(bound_file(root, selection['source']))
        require(source.get('reviewed_batch') == binding['batch'], 'Member choice must bind the presented series batch')
    choice_ref = manifest.get('delivery_scope_selection')
    if choice_ref is None:
        return plan
    choice = load(bound_file(root, choice_ref))
    original = load(bound_file(root, choice.get('series_plan')))
    units = choice.get('units')
    require(choice.get('kind') == 'partial-series-delivery' and original.get('mode') == 'series'
            and isinstance(original.get('units'), list) and len(set(original['units'])) >= 2,
            'Partial delivery must preserve a bound full series plan')
    require(isinstance(units, list) and units and len(units) == len(set(units))
            and set(units) < set(original['units']), 'Select an explicit proper subset of planned artworks')
    at = human_source(root, choice.get('source'), choice.get('quote'))
    require(at == timestamp(choice.get('decided_at')) <= datetime.now(timezone.utc), 'Preserve actual delivery scope decision time')
    # The full plan stays active; only current delivery coverage is projected.
    # A historical already-projected plan is accepted if it exactly matches.
    projected = dict(original, units=units, member_roles=[r for r in original.get('member_roles', []) if r.get('unit') in units])
    from workflow_runtime import semantics
    require(semantics(plan) == semantics(original) or semantics(plan) == semantics(projected), 'Delivery selection cannot silently rewrite the retained series plan')
    # units is AI's scope interpretation, bound above to the original plan and source.
    # Literal IDs or ordinal words in a user message do not establish its meaning.
    return projected


def delivery_decisions(root, manifest):
    result = []
    if manifest.get('delivery_scope_selection'):
        effective_series_plan(root, manifest)
        result.append(dict(kind='partial-series-delivery', record=manifest['delivery_scope_selection'],
                           original=load(bound_file(root, manifest['delivery_scope_selection']))))
    from core_return_contract import review_state
    review = review_state(root,manifest)
    for row in review.get('assessments', []):
        if row['id'] in review.get('current_assessment_ids', []):
            result.extend(assessment_confirmations(root, row).values())
    pixels_path = manifest.get('artifacts', {}).get('visual_review')
    if pixels_path:
        from review_contract import inside
        for unit in load(inside(root, pixels_path)).get('units', []):
            for product in unit.get('product_integration', []):
                record = load(bound_file(root, product['independent_confirmation']))
                raw = load(bound_file(root, record['raw_return']))
                current = dict(product['final'], version=unit['artifact']['version'], units=unit['artifact']['units'])
                result.extend(confirmations(root, product, record['raw_return'], raw, current, record['completed_at'], record.get('author_session_id')).values())
    return result
