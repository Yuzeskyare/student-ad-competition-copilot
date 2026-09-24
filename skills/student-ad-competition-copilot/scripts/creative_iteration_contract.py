"""Check recorded iteration decisions; does not score creative merit."""
from review_contract import artifact, bound_file, inside, load, read_contract

LEVERS={'core-judgment','brand-specificity','voice','explanation','originality-and-delivery'}
DELTAS={'clarity','mechanism','brand','voice','explanation_cost'}
EXPLANATION={'audience-insight','scene-evidence','language-mechanism','brand-role','claim-boundary','natural-syntax'}


def require(condition,message):
    if not condition:raise ValueError(message)


def validate_creative_iteration(root,manifest):
    if (manifest.get('schema_version')!='0.4.0' or manifest.get('category') not in {'ad-copy','marketing-plan'}
            or not (manifest.get('award_review_requested') is True or manifest.get('revision_mode')=='challenge')):
        return []
    try:
        root=root.resolve();contract,rows=read_contract(root,manifest)
        review=load(inside(root,manifest['artifacts']['creative_iteration']))
        require(review.get('run_id')==manifest['run_id'] and review.get('schema_version')=='1.0.0','Creative iteration identity mismatch')
        require(review.get('assessment_type')=='internal-diagnostic' and review.get('award_guarantee') is False,
                'Internal assessment cannot claim an actual award result or probability')
        require(isinstance(review.get('uncertainties'),list) and review['uncertainties'],'Keep explicit judging/evidence uncertainty')
        if manifest.get('award_review_requested'):
            levers=review['ceiling_review'];require(isinstance(levers,list),'Record award-ceiling diagnosis first')
            require({r['lever'] for r in levers}==LEVERS and len(levers)==len(LEVERS),'Diagnose all five possible improvement levers before rewriting')
            for row in levers:
                require(row.get('finding') in {'observed-gap','no-observed-gap','unknown'} and bool(row.get('observation')),
                        'Distinguish observed bottlenecks from unknowns')
                if row['finding']=='observed-gap':bound_file(root,row['evidence'])
            route=review['next_action']
            require(route in LEVERS|{'retain-current'},'Choose a responsibility layer or retain the current work')
            if route!='retain-current':
                diagnosis=next(r for r in levers if r['lever']==route)
                require(diagnosis['finding']=='observed-gap','Award ambition alone is not evidence that a layer needs rewriting')
        for risk in review.get('risk_actions',[]):
            require(risk.get('basis') in {'theoretical','observed-failure','official-rule','explicit-user-change'},'Classify the actual basis for reopening')
            require(risk.get('action') in {'retain','test','change'},'Unknown risk action')
            if risk['basis']=='theoretical':require(risk['action']!='change','A theoretical risk cannot automatically weaken approved copy')
            elif risk['action']=='change':bound_file(root,risk['evidence'])
        if manifest['category']=='ad-copy':
            stable=contract.get('stable_copy')
            if manifest.get('revision_mode')=='challenge':require(stable,'Challenge comparison needs the approved stable copy')
            if stable:
                require(review.get('baseline_sha256')==stable['artifact']['sha256'],'Compare with the current approved baseline')
            candidates=review['challengers'];require(isinstance(candidates,list),'Record shortlisted comparisons, or an empty list')
            ids=set();eligible=set()
            for candidate in candidates:
                ident=candidate['id'];require(ident and ident not in ids,'Challenger IDs must be unique');ids.add(ident)
                artifact(root,candidate['artifact'])
                comparison=candidate['deltas'];require(set(comparison)==DELTAS,'Separate clarity, mechanism, brand, voice and explanation-cost deltas')
                require(all(r.get('direction') in {'improved','same','regressed'} and r.get('observation') for r in comparison.values()),'Each delta needs an observed reason, not a total score')
                net_gain=any(r['direction']=='improved' for r in comparison.values()) and not any(r['direction']=='regressed' for r in comparison.values())
                checks=candidate['landing_clause_review']
                require(set(checks)=={'opening_role','landing_role','brand_replacement','natural_action','metaphor_cost'},'Review opening and landing clauses separately')
                require(all(r.get('status') in {'pass','fail','not-applicable'} and r.get('observation') for r in checks.values()),'Clause review needs actual observations')
                net_gain &= all(r['status']!='fail' for r in checks.values())
                if candidate.get('claim')=='creative-upgrade':
                    require(net_gain and any(comparison[k]['direction']=='improved' for k in ('mechanism','brand')),
                            'Clarity alone or a regressing challenger is not a creative upgrade')
                if net_gain:eligible.add(ident)
            shown=review['displayed_challenger_ids']
            require(isinstance(shown,list) and len(shown)<=5 and len(shown)==len(set(shown)) and set(shown)<=eligible,
                    'Display only challengers with recorded net gain; five is a maximum, not a quota')
            explanation=contract.get('copy_delivery',{}).get('explanation')
            if explanation:
                audit=review['explanation_review'];require(audit.get('sha256')==explanation['sha256'],'Explanation review is stale')
                checks=audit['checks'];require(set(checks)==EXPLANATION,'Review explanation insight, evidence, mechanism, brand, factual limits and syntax independently')
                require(all(r.get('status')=='pass' and r.get('observation') for r in checks.values()),'Explanation content has an observed unresolved gap')
        return [{'name':'creative-iteration-evidence','passed':True,'evidence':'Recorded routing and comparison boundaries checked; no creative merit or award prediction is machine-proven.'}]
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        return [{'name':'creative-iteration-evidence','passed':False,'evidence':str(exc)}]
