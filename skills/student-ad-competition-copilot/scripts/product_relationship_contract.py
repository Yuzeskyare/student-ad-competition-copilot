"""Current product meaning and issue severity; historical rubrics remain separate."""
from pathlib import Path

DEFINITION = (Path(__file__).resolve().parents[1] / 'references/workflow/product-relationship.md').read_text(encoding='utf-8')
HISTORICAL_DEFINITION = (Path(__file__).resolve().parents[1] / 'references/workflow/product-relationship-v1.md').read_text(encoding='utf-8')
RELEASE_020_DEFINITION = (Path(__file__).resolve().parents[1] / 'references/workflow/product-relationship-v3.md').read_text(encoding='utf-8')
PREVIOUS_DEFINITION = (Path(__file__).resolve().parents[1] / 'references/workflow/product-relationship-v2.md').read_text(encoding='utf-8')
QUESTIONS = ('product_in_core_relation', 'action_depicted_without_copy', 'claimed_relation_depicted', 'creative_scene_not_generic', 'product_action_understood_in_three_seconds')
HARD_QUESTIONS = {'product_label_consistent_readable': 'label', 'product_in_scene': 'scene-integration', 'layout_readable': 'layout'}
HINT_CODES = dict(zip(QUESTIONS, ('product-role-unreadable','action-unreadable','claim-unfulfilled','generic-scene','main-relation-ambiguous')))
PRODUCTION_CODES = {'label','scene-integration','composite','layout'}

def require(condition, reason):
    if not condition: raise ValueError(reason)

def nonempty(value): return isinstance(value, str) and bool(value.strip())

def validate_meaning(raw, blind, answers):
    relation = raw.get('product_meaning')
    require(isinstance(relation,dict) and set(relation)=={'established','observed_meaning','expected_meaning','replacement_loss','observation'}, 'Record open product meaning, expected message and concrete replacement loss')
    require(type(relation['established']) is bool and all(nonempty(relation[k]) for k in relation if k!='established'), 'Product meaning needs independent pixel evidence')
    require(relation['observed_meaning']==blind['product_role'], 'Comparison must preserve open blind product meaning')
    require(relation['established']==answers['product_in_core_relation']['answer'], 'Product meaning answer differs from independent relationship')
    require(type(blind.get('product_relation_visible')) is bool and (blind['product_relation_visible'] or not relation['established']), 'Comparison cannot invent a relationship absent from blind reading')
    meaning=raw.get('meaning_check')
    require(isinstance(meaning,dict) and set(meaning)=={'reversed','blind_observation','expected_observation','pixel_observation'} and type(meaning['reversed']) is bool and all(nonempty(meaning[k]) for k in meaning if k!='reversed'), 'Meaning reversal must name observed and expected relations and pixels')
    require(meaning['blind_observation']==blind['action'], 'Meaning reversal must preserve original blind relation')
    require(not meaning['reversed'] or answers['claimed_relation_depicted']['answer'] is False, 'A reversed main relation cannot be marked fulfilled')
    return relation

def validate_meaning_v6(raw, blind, answers):
    relation = raw.get('product_meaning')
    require(isinstance(relation,dict) and set(relation)=={'established','observed_meaning','expected_meaning','observation'}, 'Record open product meaning, expected message and pixel observation')
    require(type(relation['established']) is bool and all(nonempty(relation[k]) for k in relation if k!='established'), 'Product meaning needs independent pixel evidence')
    require(relation['observed_meaning']==blind['product_role'], 'Comparison must preserve open blind product meaning')
    require(relation['established']==answers['product_in_core_relation']['answer'], 'Product meaning answer differs from independent relationship')
    require(type(blind.get('product_relation_visible')) is bool and (blind['product_relation_visible'] or not relation['established']), 'Comparison cannot invent a relationship absent from blind reading')
    meaning=raw.get('meaning_check')
    require(isinstance(meaning,dict) and set(meaning)=={'reversed','blind_observation','expected_observation','pixel_observation'} and type(meaning['reversed']) is bool and all(nonempty(meaning[k]) for k in meaning if k!='reversed'), 'Meaning reversal must name observed and expected relations and pixels')
    require(meaning['blind_observation']==blind['action'], 'Meaning reversal must preserve original blind relation')
    require(not meaning['reversed'] or answers['claimed_relation_depicted']['answer'] is False, 'A reversed main relation cannot be marked fulfilled')
    return relation


def validate_scene_evidence(raw, answers):
    evidence=raw.get('scene_evidence')
    require(isinstance(evidence,dict) and set(evidence)=={'basis','observation'} and evidence['basis'] in {'visible-conflict','indirect-concern','no-conflict'} and nonempty(evidence['observation']), 'Scene review must distinguish an actual visible conflict from an indirect concern')
    require(evidence['observation']==answers['product_in_scene']['observation'], 'Scene evidence must preserve the original pixel observation')
    require(answers['product_in_scene']['answer'] is (evidence['basis']!='visible-conflict'), 'Only an actual visible scene conflict may fail question 7')
    if evidence['basis']=='indirect-concern':
        require(any(i.get('severity')=='hint' and i.get('question')=='brand-asset' and i.get('reason_code')=='brand-asset-pasted' and i.get('observation')==evidence['observation'] for i in raw.get('review_issues',[])), 'Cannot omit an indirect scene concern advisory')
    return evidence

def validate_issues(raw, answers):
    if 'scene_evidence' in raw: validate_scene_evidence(raw, answers)
    issues=raw.get('review_issues')
    require(isinstance(issues,list), 'Preserve every independent hard failure and advisory')
    signatures=set(); observed_issues=set()
    for issue in issues:
        require(isinstance(issue,dict) and set(issue)=={'severity','question','reason_code','observation','priority'} and issue['severity'] in {'hard','hint'} and nonempty(issue['observation']) and type(issue['priority']) is int and issue['priority']>=1, 'Issue needs severity, question, original pixels and priority')
        key=(issue['severity'],issue['question'],issue['reason_code'])
        observed_key=key+(issue['observation'],)
        require(observed_key not in observed_issues,'Duplicate independent issue'); observed_issues.add(observed_key); signatures.add(key)
        q=issue['question'];code=issue['reason_code']
        if issue['severity']=='hard':
            require((q in HARD_QUESTIONS and code==HARD_QUESTIONS[q] and answers[q]['answer'] is False and issue['observation']==answers[q]['observation']) or (q=='claimed_relation_depicted' and code=='main-relation-reversed' and raw['meaning_check']['reversed'] and issue['observation']==raw['meaning_check']['pixel_observation']) or (q=='compliance' and code=='compliance' and raw['compliance_check']['violated'] and issue['observation']==raw['compliance_check']['pixel_observation']), 'Subjective quality cannot become a hard block; preserve concrete failure evidence')
        else:
            require((q in HINT_CODES and code in {HINT_CODES[q]} | PRODUCTION_CODES and answers[q]['answer'] is False and issue['observation']==answers[q]['observation']) or (q=='layout-style' and code=='layout-style') or (q=='brand-asset' and code=='brand-asset-pasted'), 'Creative hints must preserve the independent question and reason')
    for q,code in HARD_QUESTIONS.items():
        require(answers[q]['answer'] or ('hard',q,code) in signatures, 'Cannot omit a verified text or scene failure')
    for q,code in HINT_CODES.items():
        if not answers[q]['answer']:
            require(('hint',q,code) in signatures or any(('hint',q,p) in signatures for p in PRODUCTION_CODES) or (q=='claimed_relation_depicted' and ('hard',q,'main-relation-reversed') in signatures), 'Cannot omit a subjective failure advisory')
    for issue in issues:
        if issue['severity']=='hint' and issue['question'] in HINT_CODES and issue['reason_code'] in PRODUCTION_CODES:
            source='scene-integration' if issue['reason_code']=='composite' else issue['reason_code']
            require(any(i['severity']=='hard' and i['reason_code']==source and i['question'] in HARD_QUESTIONS for i in issues), 'Production exclusion needs an independently verified corresponding failure')
    for field,code,q in [('meaning_check','main-relation-reversed','claimed_relation_depicted'),('compliance_check','compliance','compliance')]:
        check=raw.get(field,{});flag=check.get('reversed' if field=='meaning_check' else 'violated')
        require(type(flag) is bool and (not flag or ('hard',q,code) in signatures), 'Cannot omit reversal or compliance failure')
    notices=[('layout-style','layout-style',s) for s in raw.get('layout_review',{}).get('support_devices',[])]
    notices += [('brand-asset','brand-asset-pasted',r['observation']) for r in raw.get('brand_asset_review',[]) if r.get('looks_pasted')]
    for q,code,observation in notices:
        require(any(i['severity']=='hint' and i['question']==q and i['reason_code']==code and i['observation']==observation for i in issues), 'Cannot omit a recorded layout or mandatory brand advisory')
    return issues

def creative_hints(raw, answers):
    return [i for i in validate_issues(raw,answers) if i['severity']=='hint' and i['question'] in HINT_CODES and i['reason_code']==HINT_CODES[i['question']]]

def hard_failure(raw, answers):
    return any(i['severity']=='hard' for i in validate_issues(raw,answers))

def delivery_hints(raw, answers):
    issues=validate_issues(raw,answers)
    return [i['observation'] for i in sorted(issues,key=lambda i:i['priority']) if i['severity']=='hint']

def validate_direction_meaning(raw, ids):
    hints=raw.get('product_meaning_hints')
    require(isinstance(hints,list) and len(hints)==len(ids) and {h.get('direction_id') for h in hints}==set(ids), 'Every direction needs the same product-meaning advisory')
    for h in hints:
        require(set(h)=={'direction_id','audience_meaning','weak','observation'} and type(h['weak']) is bool and nonempty(h['audience_meaning']) and nonempty(h['observation']), 'Product meaning advice needs observed meaning and concrete reason')
    return hints
