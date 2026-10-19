"""Exact-artwork human confirmations and explicitly selected delivery scope.

These records change the effective decision, never the independent raw return.
Unstructured historical doubts are accepted conservatively; definite errors fail
closed. New independent returns can state judgment_basis explicitly.
"""
from datetime import datetime, timezone
import re
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


def subjective_doubt(raw, question, observation):
    if raw.get('meaning_check', {}).get('reversed') or raw.get('compliance_check', {}).get('violated'):
        return False
    if raw.get('verified_errors'):
        return False
    # A confirmed misspelling, omitted glyph, reversal or pixel conflict is not
    # an uncertainty. Do not reinterpret such a finding as a human waiver.
    text = re.sub(r'(?:未见|没有|未发现|无)(?:明显|明确|可见|任何)?(?:错字|缺字|漏字|镜像|伪字|反向|残缺)', '', observation)
    if re.search(r'错字|错写|误写|写错|写成|错别字|错误|漏字|漏掉|漏了|漏[“「\"]|缺字|缺少|缺失|缺[“「\"]|镜像|伪字|读反|反向|倒置|残缺|变形|visible.conflict|misspell|incorrect|wrong|missing|omitt|mismatch|mirrored|reversed', text, re.I):
        return False
    basis = raw.get('judgment_basis', {}).get(question)
    if basis is not None:
        return basis == 'subjective-uncertainty'
    return bool(re.search(r'无法确认|不能确认|不确定|存疑|不能判为|uncertain|cannot confirm|unable to confirm', observation, re.I))


def confirmations(root, holder, raw_ref, raw, current, completed_at):
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
        require(value is False and subjective_doubt(raw, q, observation or ''),
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
    return confirmations(root, row, record['raw_return'], raw, current, record['completed_at'])


def effective_series_plan(root, manifest):
    plan = manifest.get('series_plan', {})
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
    source = load(bound_file(root, choice['source']))
    require(all(u in source['text'] for u in units) or ('第一幅' in choice['quote'] and units == original['units'][:1]),
            'Scope source must explicitly identify selected members or the first planned member')
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
                result.extend(confirmations(root, product, record['raw_return'], raw, current, record['completed_at']).values())
    return result
