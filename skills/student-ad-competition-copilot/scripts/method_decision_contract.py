"""Method participation records; evidence binding does not certify an actual attempt."""
import re

from review_contract import bound_file
from visual_review_contract import require, nonempty

ATTEMPT_REVISION = 'attempted-not-used-v1'


def validate_method_decision(decision, revision=None):
    require(revision in {None, ATTEMPT_REVISION}, 'Unknown method decision revision')
    allowed = {'adopted', 'supporting', 'rejected'}
    if revision == ATTEMPT_REVISION:
        allowed.add('attempted-not-used')
    require(decision.get('decision') in allowed
            and nonempty(decision.get('reason')) and nonempty(decision.get('relation_or_input_change')),
            'Each method needs an adopted/supporting/rejected decision, reason and concrete participation or input change'
            if revision is None else 'Each revised method needs a supported decision, reason and concrete participation or attempted input')
    supporting = decision.get('supporting_candidate_direction_ids', [])
    require(isinstance(supporting, list) and all(nonempty(i) for i in supporting)
            and len(supporting) == len(set(supporting)), 'Supporting candidate IDs must be unique nonempty strings')
    if decision['decision'] == 'supporting':
        require(decision.get('candidate_direction_ids') == [] and bool(supporting),
                'Supporting method needs actual supporting candidates and no primary candidate IDs')
    require(decision['decision'] != 'rejected' or not supporting,
            'Rejected method cannot also claim supporting participation')
    if decision['decision'] == 'attempted-not-used':
        require(nonempty(decision.get('method_id'))
                and decision.get('candidate_direction_ids') == []
                and decision.get('supporting_candidate_direction_ids') == [],
                'Attempted-not-used method needs an ID and explicit empty primary/supporting candidates')
        evidence = decision.get('attempt_evidence')
        require(isinstance(evidence, dict) and set(evidence) == {'path', 'sha256'}
                and nonempty(evidence['path']) and isinstance(evidence['sha256'], str)
                and re.fullmatch('[0-9a-f]{64}', evidence['sha256']) is not None,
                'Attempted-not-used method needs a bound original attempt evidence file')
        require(not {'rejection_basis', 'rejection_evidence'}.intersection(decision),
                'Attempted-not-used is not an independent failure or official rejection')
    else:
        require('attempt_evidence' not in decision, 'Attempt evidence belongs only to attempted-not-used')


def validate_attempt_evidence(root, decision, *, origins=(), used=()):
    """Check immutable evidence and participation conflicts, never its truth or quality."""
    if decision['decision'] != 'attempted-not-used':
        return
    method = decision['method_id']
    require(not any(x.get('method_id') == method for x in origins),
            'Attempted-not-used method cannot have an already submitted primary candidate')
    require(method not in (used or []),
            'Attempted-not-used method cannot enter method_cards_used or method validation')
    evidence = bound_file(root, decision['attempt_evidence'])
    try:
        content = evidence.read_text(encoding='utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Attempt evidence must preserve readable original draft or derivation text') from exc
    require(bool(content.strip()), 'Attempt evidence must preserve a nonempty original draft or derivation')
