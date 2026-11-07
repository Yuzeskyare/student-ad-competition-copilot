"""Qualified method-use bindings. Applicability and actual contribution are AI judgments."""
from pathlib import Path
from review_contract import bound_file, load


def validate_usage(root, manifest):
    used = manifest.get('method_cards_used')
    if not isinstance(used, list) or not used or not all(isinstance(x, str) and x.strip() for x in used) or len(set(used)) != len(used):
        raise ValueError('Formal adoption requires nonempty unique method_cards_used; empty research may be saved but cannot pass adoption')
    if set(used).intersection(manifest.get('method_cards_rejected', [])):
        raise ValueError('Rejected methods cannot count as used')
    skill = Path(__file__).resolve().parents[1]
    pack = (skill / load(skill/'version.json')['knowledge_manifest']['path']).parent
    from knowledge_pack_contract import jsonl_rows
    from query_case_library import eligible_for_runtime, in_scope
    cards = {r['method_id']: r for r in jsonl_rows(pack/'method-cards.jsonl')}
    eligibility = load(pack/'eligibility.json')
    for ident in used:
        if ident not in cards or not eligible_for_runtime('method', cards[ident], eligibility) or not in_scope(cards[ident], manifest['competition'], manifest['category']):
            raise ValueError('Used method must be qualified in the active pack and track: '+ident)
    if manifest['category'] == 'print-ad':
        retrieval = load(bound_file(root, manifest['direction_adoption']['method_retrieval']))
        decisions = retrieval['decisions']
        from method_decision_contract import validate_method_decision, validate_attempt_evidence
        for row in decisions:
            validate_method_decision(row, retrieval.get('method_decision_revision'))
            validate_attempt_evidence(root, row, used=used)
        returned = {i for attempt in retrieval['attempts'] for i in attempt['returned_method_ids']}
        if not set(used) <= returned:
            raise ValueError('Used methods must be present in actual retrieval')
        # Existing blind-review validation checks the candidate/origin references.
        for ident in used:
            rows = [r for r in decisions if r['method_id'] == ident]
            if len(rows) != 1 or rows[0]['decision'] not in {'adopted', 'supporting'} or not (rows[0].get('candidate_direction_ids') or rows[0].get('supporting_candidate_direction_ids')):
                raise ValueError('Used method needs actual adopted/supporting participation: '+ident)
    else:
        participation = load(bound_file(root, manifest['method_participation']))
        if participation.get('run_id') != manifest['run_id'] or participation.get('selected_direction') != manifest['selected_direction']:
            raise ValueError('Method participation must bind this run and adopted direction')
        rows = participation.get('methods')
        if not isinstance(rows, list) or len(rows) != len(used) or {r.get('method_id') for r in rows} != set(used):
            raise ValueError('Document every actually used method exactly once')
        for row in rows:
            if row.get('decision') not in {'adopted', 'supporting'} or not isinstance(row.get('contribution'), str) or not row['contribution'].strip():
                raise ValueError('AI must record actual adopted/supporting contribution; attempted/rejected cannot count')
            evidence = row.get('evidence', [])
            if not isinstance(evidence, list) or not evidence or not all(bound_file(root, ref).stat().st_size for ref in evidence):
                raise ValueError('Method contribution needs bound candidate/strategy evidence')
    return dict(methods=used, applicability='AI judgment; bindings do not certify quality')


def check_usage(root, manifest):
    try:
        result = validate_usage(root, manifest)
        return dict(name='qualified-method-use', passed=True, evidence=result)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return dict(name='qualified-method-use', passed=False, evidence=str(exc))
