"""Three model retries, independently checked changes, and a preserved final handback."""
import json
import re
import unicodedata
from datetime import datetime, timezone

CONTRACT = 'print-model-redivergence-v1'
LIMIT = 3
AXES = {'starting-point-type', 'visual-language', 'core-mechanism'}
RUBRIC = '''你是空上下文独立轮次变化检查者，不生图，不替作者补充创意。只看上轮与本轮实际方向句、各自独立排序和作者登记的变化。逐项核对起点类型、视觉语言或核心机制是否实质变化，换词、换名称、换色而关系未变不算。提取上轮和本轮每个保留方向的核心机制；本轮机制与上轮语义重复时在previous_matches列出对应上轮ID，即使措辞不同。判断整轮是否只重复上轮机制。返回JSON：changes逐项保留axis/before/after并增加substantive布尔和reason；previous_mechanisms逐项direction_id/mechanism；current_mechanisms逐项direction_id/mechanism/previous_matches数组；round_repeats_previous_mechanism布尔（本轮所有机制都在上轮出现时true）。不按品类设分支，不把作者自述当作变化成立。'''


def enabled(manifest):
    value = manifest.get('direction_redivergence_contract')
    if value not in {None, CONTRACT}:
        raise ValueError('Unknown model re-divergence contract')
    return value == CONTRACT


def limit(manifest):
    return LIMIT if enabled(manifest) else 1


def normalize(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value).casefold())


def request(previous, current, changes):
    return RUBRIC + '\n' + json.dumps(dict(previous=previous, current=current, changes=changes), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def round_input(root, reference):
    from validate_print_ad_run import load_json, bound_file
    record = load_json(bound_file(root, reference))
    return dict(sentences=json.loads(bound_file(root, record['inputs'][0]['file']).read_text(encoding='utf-8')),
                ranking=record['result']['ranking']), record


def validate(root, manifest, bundle, inherited_used=0):
    from validate_print_ad_run import load_json, bound_file, timestamp, validate_direction_blind_review
    def require(value, reason):
        if not value:
            raise ValueError(reason)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    if not enabled(manifest):
        return
    require(manifest.get('direction_contract') in {'print-direction-v6','print-direction-v7','print-direction-v8','print-direction-v9','print-direction-v10','print-direction-v11','print-direction-v12'}, 'Three retries require an independent direction contract')
    state = bundle['redivergence']
    require(isinstance(state,dict) and set(state) <= {'transitions','legacy_manifest','exhausted_handoff'} and 'transitions' in state,
            'Model retry state needs transitions and optional immutable legacy evidence')
    rounds = bundle['rounds']
    require(inherited_used + len(rounds)-1 <= LIMIT, 'At most three model-initiated re-divergences are allowed')
    start = 1
    if 'legacy_manifest' in state:
        old = load_json(bound_file(root, state['legacy_manifest']))
        require(not enabled(old) and old['run_id']==manifest['run_id'], 'Legacy retry evidence must bind this run before the new contract')
        require(validate_direction_blind_review(root,old)['passed'], 'Legacy direction evidence must remain valid')
        original = load_json(bound_file(root,old['direction_adoption']['blind_review']))
        require(rounds[:len(original['rounds'])]==original['rounds'], 'Preserve the complete immutable legacy round prefix')
        start = len(original['rounds'])
    transitions = state['transitions']
    require(isinstance(transitions,list) and len(transitions)==len(rounds)-start,
            'Every new automatic round needs a registered change and independent transition check')
    round_records=[load_json(bound_file(root,r)) for r in rounds]
    sessions={r['checker_session_id'] for r in round_records if r.get('checker_session_id')}
    calls={r['invocation_id'] for r in round_records if r.get('invocation_id')}
    for index, reference in enumerate(transitions,start):
        event = load_json(bound_file(root,reference))
        require(set(event)=={'previous_round','current_round','registered_at','changes','independent_check'}
                and event['previous_round']==rounds[index-1] and event['current_round']==rounds[index],
                'Transition must bind the actual immediately preceding and current rounds')
        previous, before = round_input(root,rounds[index-1])
        current, after = round_input(root,rounds[index])
        registered=timestamp(event['registered_at'])
        require(timestamp(before['completed_at']) < registered <= timestamp(after['input_prepared_at']),
                'Register the changed thinking after the previous result and before the next input')
        changes=event['changes']
        require(isinstance(changes,list) and bool(changes)
                and all(isinstance(x,dict) and set(x)=={'axis','before','after'} and x['axis'] in AXES
                        and text(x['before']) and text(x['after']) for x in changes)
                and len({x['axis'] for x in changes})==len(changes),
                'Register concrete before/after starting point, visual language or core mechanism changes')
        record=load_json(bound_file(root,event['independent_check']))
        require(set(record)=={'checker_context','author_session_id','checker_session_id','invocation_id','started_at','completed_at','request','raw_return','result'}
                and record['checker_context']=='fresh-isolated' and text(record['author_session_id'])
                and text(record['checker_session_id']) and record['checker_session_id']!=record['author_session_id']
                and text(record['invocation_id']), 'A fresh independent transition checker is required')
        require(record['checker_session_id'] not in sessions and record['invocation_id'] not in calls,
                'Each transition needs a fresh independent checker invocation')
        sessions.add(record['checker_session_id']);calls.add(record['invocation_id'])
        require(timestamp(after['completed_at']) <= timestamp(record['started_at']) <= timestamp(record['completed_at']) <= timestamp(bundle['recorded_at']) <= datetime.now(timezone.utc),
                'Independent transition check must follow the current return and precede the bundle')
        require(bound_file(root,record['request']).read_text(encoding='utf-8')==request(previous,current,changes),
                'Transition request must bind the fixed rubric and both actual direction rounds')
        raw=load_json(bound_file(root,record['raw_return']))
        require(raw==record['result'] and set(raw)=={'changes','previous_mechanisms','current_mechanisms','round_repeats_previous_mechanism'},
                'Preserve the complete original independent transition return')
        judgments=raw['changes']
        require(isinstance(judgments,list) and len(judgments)==len(changes)
                and all(isinstance(j,dict) and set(j)=={'axis','before','after','substantive','reason'}
                        and {k:j[k] for k in ('axis','before','after')}==c and type(j['substantive']) is bool
                        and text(j['reason']) for c,j in zip(changes,judgments)),
                'Each registered change needs its unchanged independent substantive judgment')
        require(any(j['substantive'] and normalize(j['before'])!=normalize(j['after']) for j in judgments),
                'No substantive change of thinking; this round is not a qualified retry')
        previous_ids={x['direction_id'] for x in previous['ranking']}
        current_ids={x['direction_id'] for x in current['ranking']}
        profiles=raw['previous_mechanisms'];new=raw['current_mechanisms']
        require(isinstance(profiles,list) and len(profiles)==len(previous_ids)
                and all(set(x)=={'direction_id','mechanism'} and text(x['mechanism']) for x in profiles)
                and {x['direction_id'] for x in profiles}==previous_ids,
                'Extract every previously retained direction mechanism')
        require(isinstance(new,list) and len(new)==len(current_ids)
                and all(set(x)=={'direction_id','mechanism','previous_matches'} and text(x['mechanism'])
                        and isinstance(x['previous_matches'],list) and len(x['previous_matches'])==len(set(x['previous_matches']))
                        and set(x['previous_matches'])<=previous_ids for x in new)
                and {x['direction_id'] for x in new}==current_ids,
                'Check every current retained mechanism against the previous round')
        for item in new:
            exact={p['direction_id'] for p in profiles if normalize(p['mechanism'])==normalize(item['mechanism'])}
            require(exact<=set(item['previous_matches']), 'Identical mechanisms cannot be reported as novel by changing IDs')
        repeated=all(x['previous_matches'] for x in new)
        require(type(raw['round_repeats_previous_mechanism']) is bool and raw['round_repeats_previous_mechanism']==repeated,
                'Round repetition must agree with every independent mechanism comparison')
        require(not repeated, 'This round repeats the previous mechanisms; it is not a qualified retry')
    if len(rounds)>1 and inherited_used+len(rounds)-1==LIMIT and load_json(bound_file(root,rounds[-1]))['result']['all_weak']:
        require('exhausted_handoff' in state, 'After three retries still weak: stop and hand all round rankings and reasons to the user')
        handoff=load_json(bound_file(root,state['exhausted_handoff']))
        expected=[dict(round=r,ranking=load_json(bound_file(root,r))['result']['ranking'],trope_screen=load_json(bound_file(root,r))['result']['trope_screen']) for r in rounds]
        require(set(handoff)=={'state','rounds','user_facing_copy'} and handoff['state']=='stopped' and handoff['rounds']==expected,
                'Exhausted handback must preserve all original round rankings and reasons')
        visible=bound_file(root,handoff['user_facing_copy']).read_text(encoding='utf-8')
        require(all(x['direction_id'] in visible and x['reason'] in visible for r in expected for x in r['ranking']+r['trope_screen']),
                'Show all original round rankings and reasons in the user handback')
