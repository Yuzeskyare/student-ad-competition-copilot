"""Recover an already explicit choice without inventing a past review or release."""
import json
import re
from datetime import datetime, timezone
from review_contract import bound_file, load, human_source, timestamp


def validate_interpretation(root, event, recovery):
    """Check AI-authored data and bindings, never the meaning of the user's words."""
    intent = recovery.get('interpretation')
    fields = {'actor', 'source', 'context', 'decision', 'label', 'candidate_id',
              'scope_note', 'recorded_at'}
    if not isinstance(intent, dict) or set(intent) != fields or intent['actor'] != 'assistant':
        raise ValueError('Record a current AI interpretation from the saved conversation; preserve the original choice, do not ask the user to choose again')
    if intent['source'] != event['source']:
        raise ValueError('AI interpretation must bind the original user source')
    context = intent['context']
    if not isinstance(context, list) or recovery['choice_list_source'] not in context:
        raise ValueError('AI interpretation must bind the original choice list and relevant context')
    for reference in context:
        bound_file(root, reference)
    if intent['decision'] not in {'selected', 'withdrawn', 'unresolved'}:
        raise ValueError('Unknown AI interpretation decision')
    if intent['decision'] != 'selected':
        raise ValueError('AI recorded no current selection; do not adopt a direction')
    if intent['label'] != recovery['label'] or intent['candidate_id'] != recovery['candidate_id']:
        raise ValueError('AI interpretation and recovered candidate mapping differ')
    if not isinstance(intent['scope_note'], str) or not intent['scope_note'].strip():
        raise ValueError('AI must record the interpreted direction and scope separately from the user quote')
    if not timestamp(event['decided_at']) <= timestamp(intent['recorded_at']) <= timestamp(recovery['recovered_at']):
        raise ValueError('Interpretation is a current record, not a rewritten historical choice')
    # Passing here proves only structure/source consistency. It does not certify
    # the assistant's semantic interpretation or grant production permission.


def candidate_projection(original, basis_type, prose_projection=None):
    if prose_projection is not None:
        candidate = prose_projection['candidate']
        if candidate.get('direction_id') != original['id'] or candidate.get('basis_type') != basis_type:
            raise ValueError('Current projection must retain the mapped ID and declared basis type')
        from validate_print_ad_run import validate_direction_sentence_v5
        validate_direction_sentence_v5(candidate)
        return candidate
    """Expose the literal untyped legacy basis without rewriting the chosen sentence."""
    statement = original['statement']
    parts = statement.split('；创意依据：')
    if len(parts) != 2 or not parts[0].strip() or not parts[1].endswith('。') or not parts[1][:-1].strip():
        raise ValueError('Recovery requires an explicit original creative basis; do not invent one')
    from validate_print_ad_run import DIRECTION_BASIS_TYPES
    if basis_type not in DIRECTION_BASIS_TYPES:
        raise ValueError('AI must classify the original basis using an existing type; no inferred default')
    candidate = dict(direction_id=original['id'], statement=statement,
                     basis_type=basis_type, basis=parts[1][:-1])
    # Only the old untyped suffix is tolerated. All ordinary sentence constraints apply.
    from validate_print_ad_run import validate_direction_sentence_v5
    typed = dict(candidate, statement=parts[0]+'；创意依据（'+DIRECTION_BASIS_TYPES[candidate['basis_type']]+'）：'+candidate['basis']+'。')
    validate_direction_sentence_v5(typed)
    return candidate


def evidence(root, event):
    r = load(bound_file(root, event['selection_recovery']))
    if 'interpretation' not in r:
        raise ValueError('Record a current AI interpretation from saved context; preserve the original choice and do not ask the user to choose again')
    if 'basis_type' not in r:
        raise ValueError('AI must classify the saved original basis in a new recovery snapshot; preserve the original choice')
    fields = {'candidate_id', 'label', 'basis_type', 'candidates', 'choice_list_source', 'mapping_quote',
              'author_notes', 'exploratory_review', 'native_user_event', 'recovered_at', 'interpretation'}
    prose = r.get('prose_projection')
    if prose is not None:
        fields.add('prose_projection')
    if set(r) != fields:
        raise ValueError('Selection recovery needs original candidate, mapping, notes, review and native user event')
    candidates = load(bound_file(root, r['candidates']))['candidates']
    matches = [c for c in candidates if c['id'] == r['candidate_id']]
    if len(matches) != 1:
        raise ValueError('Recovered candidate must resolve exactly once in the original candidates')
    choices = bound_file(root, r['choice_list_source']).read_text(encoding='utf-8')
    if prose is None:
        # Parse the table format only, never the natural-language user instruction.
        label_rows = []
        for line in choices.splitlines():
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) >= 2 and re.fullmatch(re.escape(r['label']) + r'(?:\s+.*)?', cells[0], re.I):
                label_rows.append((line, cells[1]))
        if len(label_rows) != 1 or label_rows[0] != (r['mapping_quote'], r['candidate_id']):
            raise ValueError('Recovered label must resolve to exactly one original choice-list row and candidate')
    else:
        if not isinstance(prose, dict) or set(prose) != {'actor', 'candidate', 'source_quotes', 'recorded_at', 'native_choice_event', 'details'} or prose['actor'] != 'assistant':
            raise ValueError('Record a current assistant-authored projection, not a historical quotation')
        shown = load(bound_file(root, prose['native_choice_event']))
        message = shown.get('payload', {})
        shown_text = ''.join(x.get('text', '') for x in message.get('content', []) if x.get('type') == 'output_text')
        if (message.get('type') != 'message' or message.get('role') != 'assistant'
                or message.get('status') != 'completed' or shown_text != choices
                or timestamp(shown['timestamp']) > timestamp(event['decided_at'])):
            raise ValueError('Choice list must equal the actual completed assistant message shown before the user choice')
        details = prose['details']
        if not isinstance(details, list):
            raise ValueError('Current refinements must be an explicit list')
        for detail in details:
            if (not isinstance(detail, dict) or set(detail) != {'source', 'quote', 'recorded_at'}
                    or detail['source'] not in r['interpretation']['context']):
                raise ValueError('Current refinements require source, quote, time and interpretation context binding')
            detail_text = bound_file(root, detail['source']).read_text(encoding='utf-8')
            if (not isinstance(detail['quote'], str) or not detail['quote'].strip()
                    or detail_text.count(detail['quote']) != 1
                    or not timestamp(event['decided_at']) <= timestamp(detail['recorded_at']) <= timestamp(prose['recorded_at'])):
                raise ValueError('Current refinement must quote its source exactly and precede projection')
        quote = r['mapping_quote']
        quotes = prose['source_quotes']
        if (not isinstance(quote, str) or not quote.strip() or choices.count(quote) != 1
                or not isinstance(quotes, list) or not quotes
                or any(not isinstance(q, str) or not q.strip() or choices.count(q) != 1 or q not in quote for q in quotes)):
            raise ValueError('Original mapping and supporting quotations must occur uniquely and exactly in the saved choice list')
        original = matches[0]
        if (original.get('statement') != quote or original.get('starting_point') not in {'consumer-moment', 'product-benefit', 'counter-intuitive'}
                or not isinstance(original.get('starting_point_quote'), str)
                or not original['starting_point_quote'].strip() or original['starting_point_quote'] not in quote):
            raise ValueError('Current candidate mapping must bind the original excerpt and starting-point quote')
        if not timestamp(event['decided_at']) <= timestamp(prose['recorded_at']) <= timestamp(r['recovered_at']):
            raise ValueError('Projection must be recorded currently, after the original choice')
        candidate_projection(original, r['basis_type'], prose)
    source = load(bound_file(root, event['source']))
    native = load(bound_file(root, r['native_user_event']))
    item = native.get('payload', {}).get('item', {})
    text = ''.join(x.get('text', '') for x in item.get('content', []) if x.get('type') == 'text')
    if (item.get('type') != 'UserMessage' or item.get('id') != source['event_id'] or
            event['quote'].strip() != text.strip() or source['text'].strip() != text.strip() or
            timestamp(native['timestamp']) != timestamp(event['decided_at']) or
            human_source(root, event['source'], event['quote']) != timestamp(event['decided_at'])):
        raise ValueError('Recovery must retain the exact original native user choice, scope and time')
    for key in ('author_notes', 'exploratory_review'):
        if not bound_file(root, r[key]).read_text(encoding='utf-8').strip():
            raise ValueError('Preserve original exploration and attempted-not-used evidence')
    if not timestamp(event['decided_at']) < timestamp(r['recovered_at']) <= datetime.now(timezone.utc):
        raise ValueError('Recovery is recorded now; never backdate a formal check')
    validate_interpretation(root, event, r)
    return r, matches[0]


def validate_selection(root, event, selection, adoption, candidate, result, completed):
    r, original = evidence(root, event)
    if (selection.get('recovery') != event['selection_recovery'] or selection['kind'] != 'user-choice'
            or selection['source'] != event['source'] or selection['statement'] != event['quote']
            or timestamp(selection['decided_at']) != timestamp(event['decided_at'])
            or candidate != candidate_projection(original, r['basis_type'], r.get('prose_projection'))
            or selection['direction_id'] != original['id']):
        raise ValueError('Recovery must preserve the original choice and byte-identical direction sentence')
    at = timestamp(r['recovered_at'])
    if not completed <= at < timestamp(adoption['adopted_at']):
        raise ValueError('New formal review must precede current recovery and adoption')
    # The old exploratory ranking did not disclose a formal override judgment.
    # Never manufacture consent for a newly detected ineligible/non-drawable choice.
    screen = next(x for x in result['trope_screen'] if x['direction_id'] == original['id'])
    drawable = next(x['drawable'] for x in result['drawability'] if x['direction_id'] == original['id'])
    if screen['is_trope'] or screen['counterexample_matches'] or not drawable or selection.get('user_override'):
        raise ValueError('Recovery cannot invent an informed override of a new formal failure')
    return at
