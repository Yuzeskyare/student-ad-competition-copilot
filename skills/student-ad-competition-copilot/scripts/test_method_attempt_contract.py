#!/usr/bin/env python3
"""SYNTHETIC record tests. No model calls, actual creative claims or production."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time

from jsonschema import Draft202012Validator, ValidationError
from method_decision_contract import ATTEMPT_REVISION, validate_method_decision, validate_attempt_evidence
from review_contract import digest


def main():
    schema = json.loads((Path(__file__).resolve().parents[1] / 'references/schemas/print-ad-run-manifest.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator({'$ref':'#/$defs/method_retrieval_supporting', '$defs':schema['$defs']})
    checks = []

    def expect(label, accepted, call):
        try:
            call()
        except (ValueError, OSError, ValidationError) as exc:
            assert not accepted, (label, str(exc))
            checks.append({'case':label, 'passed':True, 'rejected':str(exc)})
        else:
            assert accepted, label
            checks.append({'case':label, 'passed':True})

    with tempfile.TemporaryDirectory(prefix='synthetic-method-attempt-', dir=Path.cwd()) as temp:
        root = Path(temp)
        source = root/'attempt.txt'
        source.write_text('SYNTHETIC original drafting exercise: wrote three phrase variants; retained none.\n', encoding='utf-8')
        evidence = {'path':'attempt.txt', 'sha256':digest(source)}
        unused = dict(method_id='SYNTHETIC-unused', decision='attempted-not-used',
                      reason='SYNTHETIC wrote three variants, none retained',
                      relation_or_input_change='SYNTHETIC no retained input change',
                      candidate_direction_ids=[], supporting_candidate_direction_ids=[], attempt_evidence=evidence)
        used = dict(method_id='SYNTHETIC-used', decision='adopted', reason='SYNTHETIC actually used',
                    relation_or_input_change='SYNTHETIC changed the retained relation', candidate_direction_ids=['D1'],
                    supporting_candidate_direction_ids=[])
        retrieval = dict(run_id='SYNTHETIC-run', recorded_at='2026-10-27T00:00:00+00:00', original_problem='SYNTHETIC problem',
                         method_decision_revision=ATTEMPT_REVISION,
                         attempts=[dict(output=evidence, fallback_terms=[], returned_method_ids=['SYNTHETIC-unused','SYNTHETIC-used'])],
                         decisions=[used, unused])

        def check_record(record=retrieval, origins=(), methods=()):
            validator.validate(record)
            for decision in record['decisions']:
                validate_method_decision(decision, record.get('method_decision_revision'))
                validate_attempt_evidence(root, decision, origins=origins, used=methods)

        expect('actual-attempt-record-with-separate-used-method', True,
               lambda:check_record(origins=[{'method_id':'SYNTHETIC-used','direction_id':'D1'}], methods=['SYNTHETIC-used']))
        legacy = deepcopy(retrieval); legacy.pop('method_decision_revision'); legacy['decisions'] = [used]
        expect('legacy-three-state-record', True, lambda:check_record(legacy))
        for state in ['adopted','supporting','rejected']:
            decision = deepcopy(used); decision['decision'] = state
            if state == 'supporting': decision.update(candidate_direction_ids=[], supporting_candidate_direction_ids=['D1'])
            expect('legacy-'+state, True, lambda d=decision:validate_method_decision(d))
        expect('legacy-runtime-rejects-new-state', False, lambda:validate_method_decision(unused))
        missing_revision = deepcopy(retrieval); missing_revision.pop('method_decision_revision')
        expect('legacy-schema-rejects-new-state', False, lambda:check_record(missing_revision))
        unknown_revision = deepcopy(retrieval); unknown_revision['method_decision_revision'] = 'unknown'
        expect('unknown-revision', False, lambda:check_record(unknown_revision))
        legacy_evidence = deepcopy(used); legacy_evidence['attempt_evidence'] = evidence
        expect('legacy-cannot-hide-attempt-evidence', False, lambda:validate_method_decision(legacy_evidence))

        for label, mutate in [
            ('missing-attempt-evidence', lambda d:d.pop('attempt_evidence')),
            ('missing-explicit-primary-list', lambda d:d.pop('candidate_direction_ids')),
            ('missing-explicit-supporting-list', lambda d:d.pop('supporting_candidate_direction_ids')),
            ('claimed-primary-candidate', lambda d:d.update(candidate_direction_ids=['D1'])),
            ('claimed-supporting-candidate', lambda d:d.update(supporting_candidate_direction_ids=['D1'])),
            ('rejection-is-not-unused-attempt', lambda d:d.update(rejection_basis='observed-failure')),
            ('missing-attempt-description', lambda d:d.update(reason=' ')),
            ('invalid-evidence-hash-shape', lambda d:d.update(attempt_evidence={'path':'attempt.txt','sha256':'bad'})),
        ]:
            bad = deepcopy(unused); mutate(bad)
            expect(label, False, lambda d=bad:validate_method_decision(d, ATTEMPT_REVISION))
        expect('already-submitted-origin', False,
               lambda:check_record(origins=[{'method_id':'SYNTHETIC-unused','direction_id':'D2'}]))
        expect('cannot-contribute-to-method-validation', False,
               lambda:check_record(methods=['SYNTHETIC-used','SYNTHETIC-unused']))
        bad_hash = deepcopy(unused); bad_hash['attempt_evidence']['sha256'] = '0'*64
        expect('changed-evidence', False, lambda:validate_attempt_evidence(root, bad_hash))
        source.write_text('   ', encoding='utf-8')
        empty = deepcopy(unused); empty['attempt_evidence']['sha256'] = digest(source)
        expect('empty-original-draft', False, lambda:validate_attempt_evidence(root, empty))
        outside = deepcopy(unused); outside['attempt_evidence']['path'] = '../outside.txt'
        expect('evidence-path-escape', False, lambda:validate_attempt_evidence(root, outside))
        source.write_bytes(b'\xff\xfe\xfa')
        binary = deepcopy(unused); binary['attempt_evidence']['sha256'] = digest(source)
        expect('unreadable-original-text', False, lambda:validate_attempt_evidence(root, binary))

        # Exercise the actual creative-contract retrieval entry, not just its
        # helper. Direction approval is intentionally absent in this record test.
        import validate_print_ad_run as integrated
        skill = Path(__file__).resolve().parents[1]
        problem = 'SYNTHETIC record integration 产品 关系'
        query_file = root/'entry-query.json'
        subprocess.run([sys.executable, '-B', str(skill/'scripts/query_case_library.py'),
                        '--kind','method','--competition','academy-award','--category','print-ad',
                        '--problem',problem,'--limit','1','--output',str(query_file)],
                       check=True, capture_output=True, text=True, encoding='utf-8')
        query = json.loads(query_file.read_text(encoding='utf-8'))
        method_ids = [row['record']['method_id'] for row in query['results']]
        assert method_ids, 'Synthetic entry test needs an actual qualified method query result'
        source.write_text('SYNTHETIC original three-phrase drafting trial; no phrase retained.\n', encoding='utf-8')
        entry_decision = deepcopy(unused)
        entry_decision.update(method_id=method_ids[0], attempt_evidence={'path':'attempt.txt','sha256':digest(source)})
        recorded = datetime.now(timezone.utc)
        entry_retrieval = dict(retrieval, original_problem=problem, recorded_at=recorded.isoformat(),
                               attempts=[dict(output={'path':'entry-query.json','sha256':digest(query_file)},
                                              fallback_terms=[],returned_method_ids=method_ids)],
                               decisions=[entry_decision])
        retrieval_file = root/'entry-retrieval.json'
        retrieval_file.write_text(json.dumps(entry_retrieval,ensure_ascii=False),encoding='utf-8')
        while datetime.now(timezone.utc) <= recorded:
            time.sleep(0.001)
        (root/'entry-gates.json').write_text(json.dumps({'definition_set_id':'print-ad.0.22.0'}),encoding='utf-8')
        manifest = dict(run_id='SYNTHETIC-run',competition='academy-award',run_scope='concept-only',
                        creative_contract='print-core-v4',direction_contract='print-direction-v12',
                        product_contract='print-product-v3',core_review_contract='print-core-product-v8',
                        selected_direction='D1',artifacts={'quality_gate_results':'entry-gates.json'},
                        direction_adoption={'direction_id':'D1','adopted_at':datetime.now(timezone.utc).isoformat(),
                                            'method_retrieval':{'path':'entry-retrieval.json','sha256':digest(retrieval_file)}})

        def check_entry(should_pass, methods=()):
            result = integrated.validate_creative_contract(root,dict(manifest,method_cards_used=list(methods)))
            method_check = next(row for row in result if row['name']=='method-retrieval-before-adoption')
            assert method_check['passed'] == should_pass, method_check
            if not should_pass:
                assert 'cannot enter method_cards_used' in str(method_check['evidence']), method_check
            assert not next(row for row in result if row['name']=='independent-direction-blind-review')['passed'], result

        expect('creative-entry-accepts-revised-attempt-without-granting-direction-approval', True,
               lambda:check_entry(True))
        expect('creative-entry-rejects-attempted-method-used-even-before-method-validation', True,
               lambda:check_entry(False, method_ids))
    print(json.dumps({'status':'passed', 'checks':len(checks), 'synthetic':True,
                      'boundary':'Checks evidence binding and participation conflicts, not truth, actual drafting or creative quality.',
                      'results':checks}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
