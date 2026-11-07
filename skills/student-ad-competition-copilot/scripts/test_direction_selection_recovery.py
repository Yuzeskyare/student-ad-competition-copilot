"""Binding regressions; synthetic fixtures do not test language understanding."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from direction_change_contract import validate_change
from pathlib import Path
from review_contract import digest
from direction_selection_recovery import evidence, candidate_projection

class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.decided = '2020-01-02T00:00:00Z'
        self.quote = '选择 A'
        self.choices = '候选方向\nA 标题\n原始画面及起点\nB 标题\n其他'
        self.mapping = 'A 标题\n原始画面及起点'
        self.listref = self.save('choice.txt', self.choices, False)
        self.native_list = self.save('display.json', {'timestamp':'2020-01-01T00:00:00Z','payload':{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':self.choices}]}})
        self.native = self.save('user.json', {'timestamp':self.decided,'payload':{'item':{'type':'UserMessage','id':'id1','content':[{'type':'text','text':self.quote}]}}})
        self.source = self.save('source.json', {'kind':'user-message','actor_type':'human','event_id':'id1','text':self.quote,'occurred_at':self.decided})
        self.notes = self.save('notes.txt', '原始探索记录', False)
        self.detail = self.save('details.txt', '当前制作细化：具体文案', False)
        self.candidate = {'direction_id':'R2','statement':'产品屏幕显示记录；创意依据（人的时刻或洞察）：提出疑问。','basis_type':'consumer-moment','basis':'提出疑问'}
        self.candidates = self.save('candidates.json', {'candidates':[{'id':'R2','statement':self.mapping,'starting_point':'consumer-moment','starting_point_quote':'原始画面及起点'}]})
        self.recovery = {'candidate_id':'R2','label':'A','basis_type':'consumer-moment','candidates':self.candidates,'choice_list_source':self.listref,'mapping_quote':self.mapping,'author_notes':self.notes,'exploratory_review':self.notes,'native_user_event':self.native,'recovered_at':'2020-01-05T00:00:00Z','interpretation':{'actor':'assistant','source':self.source,'context':[self.listref,self.detail],'decision':'selected','label':'A','candidate_id':'R2','scope_note':'保留原方向','recorded_at':'2020-01-03T00:00:00Z'},'prose_projection':{'actor':'assistant','candidate':self.candidate,'source_quotes':['原始画面及起点'],'recorded_at':'2020-01-04T00:00:00Z','native_choice_event':self.native_list,'details':[{'source':self.detail,'quote':'具体文案','recorded_at':'2020-01-03T00:00:00Z'}]}}
        self.event = {'source':self.source,'quote':self.quote,'decided_at':self.decided}
    def tearDown(self): self.tmp.cleanup()
    def save(self,name,value,as_json=True):
        p=self.root/name
        p.write_text(json.dumps(value,ensure_ascii=False) if as_json else value,encoding='utf8')
        return {'path':name,'sha256':digest(p)}
    def check(self, value=None):
        self.event['selection_recovery']=self.save('recovery.json',value or self.recovery)
        return evidence(self.root,self.event)
    def test_valid_and_projection(self):
        rec, original=self.check()
        self.assertEqual(candidate_projection(original,rec['basis_type'],rec['prose_projection']),self.candidate)
    def test_changed_source_rejected(self):
        (self.root/'choice.txt').write_text(self.choices+'x',encoding='utf8')
        with self.assertRaises(ValueError): self.check()
    def test_fake_quote_rejected(self):
        r=copy.deepcopy(self.recovery); r['prose_projection']['source_quotes']=['并不存在']
        with self.assertRaises(ValueError): self.check(r)
    def test_duplicate_mapping_rejected(self):
        r=copy.deepcopy(self.recovery); r['mapping_quote']='标题'
        with self.assertRaises(ValueError): self.check(r)
    def test_late_display_rejected(self):
        r=copy.deepcopy(self.recovery); r['prose_projection']['native_choice_event']=self.save('late.json',{'timestamp':'2020-01-03T00:00:00Z','payload':{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':self.choices}]}})
        with self.assertRaises(ValueError): self.check(r)
    def test_detail_must_precede_projection(self):
        r=copy.deepcopy(self.recovery); r['prose_projection']['details'][0]['recorded_at']='2020-01-05T00:00:00Z'
        with self.assertRaises(ValueError): self.check(r)
    def test_user_timestamp_not_substituted(self):
        self.event['decided_at']='2020-01-02T00:00:01Z'
        with self.assertRaises(ValueError): self.check()
    def test_legacy_table_evidence(self):
        r=copy.deepcopy(self.recovery)
        r.pop('prose_projection')
        row='| A 标题 | R2 | 画面 |'
        r['choice_list_source']=self.save('legacy.txt','| 标签 | ID | 内容 |\n'+row,False)
        r['mapping_quote']=row
        r['candidates']=self.save('legacy.json',{'candidates':[{'id':'R2','statement':'画面有产品；创意依据：提出疑问。','starting_point':'consumer-moment'}]})
        r['interpretation']['context']=[r['choice_list_source']]
        result, original=self.check(r)
        self.assertEqual(original['id'],'R2')
        self.assertEqual(candidate_projection(original,result['basis_type'])['basis'],'提出疑问')

    def test_informal_baseline_requires_no_invented_adoption(self):
        recovery_ref=self.save('recovery.json',self.recovery)
        base={'run_id':'run','competition':'c','category':'print','creative_contract':'x','direction_contract':'y'}
        baseline=self.save('base.json',base)
        event={'kind':'user-direction-change','action':'recover-selection','source':self.source,'quote':self.quote,'decided_at':self.decided,'previous_manifest':baseline,'selection_recovery':recovery_ref}
        event_ref=self.save('event.json',event)
        selection=self.save('selection.json',{'source':self.source,'statement':self.quote,'decided_at':self.decided})
        first=self.save('round.json',{'input_prepared_at':'2020-01-04T00:00:00Z'})
        bundle=self.save('bundle.json',{'rounds':[first]})
        adoption={'user_direction_change':event_ref,'previous_adoptions':[],'selection_mode':'user','selection_record':selection,'blind_review':bundle,'claim_lock':self.notes,'method_retrieval':self.notes,'adopted_at':'2020-01-06T00:00:00Z'}
        manifest=dict(base,direction_adoption=adoption)
        with patch('validate_print_ad_run.validate_direction_blind_review', side_effect=AssertionError('must not invent prior check')), patch('validate_print_ad_run.load_claim_lock', side_effect=AssertionError('must not invent prior lock')), patch('direction_redivergence_contract.limit', return_value=1):
            result=validate_change(self.root,manifest)
        self.assertTrue(result['recovered'])
        adoption['previous_adoptions']=[{'fake':'adoption'}]
        with self.assertRaises(ValueError): validate_change(self.root,manifest)

    def test_legacy_projection_kept(self):
        original={'id':'R2','statement':'画面有产品；创意依据：提出疑问。'}
        result=candidate_projection(original,'consumer-moment')
        self.assertEqual(result['statement'],original['statement'])

if __name__ == '__main__': unittest.main()
