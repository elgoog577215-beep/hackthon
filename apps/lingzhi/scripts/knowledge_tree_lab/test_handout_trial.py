"""Checks for handout revision/reference authority, independent of live APIs."""
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from .handout_trial import inspect,render,project_applications


def fixture():
    point={'key':'K-T01','knowledge_id':'kp_1','name':'测试规则','source_refs':['S1']}
    example={'key':'E-T01','title':'例题','knowledge_keys':['K-T01'],'code':'puts("2");','answer_stdout':'2\n'}
    bundle={'topic':'types','title':'标题','knowledge_revision':'revision-a','terminology_revision':'terms-a',
        'points':[point],'terminology':[{'key':'term','canonical':'术语','aliases':[]}],
        'sections':[{'key':'s','required_knowledge_keys':['K-T01']}],
        'example_bank':[example],'exercise_bank':[],
        'diagnostic':{'key':'D-T','knowledge_keys':['K-T01']}}
    block={'kind':'explanation','heading':'规则','text':'术语的正确规则。','knowledge_keys':['K-T01'],'term_keys':['term'],'example_key':None,'diagnostic_key':None}
    doc={'title':'标题','knowledge_revision':'revision-a','terminology_revision':'terms-a',
         'introduction':'引入','sections':[{'key':'s','title':'小节','blocks':[block]}],'exercise_keys':[],'unresolved':[]}
    return bundle,doc


class HandoutTests(unittest.TestCase):
    def test_projection_keeps_in_scope_composite_application(self):
        source=[{'id':'nested','knowledge_ids':['p1','p2'],'answer':'保持这份答案'},
                {'id':'foreign','knowledge_ids':['p1','outside'],'answer':'不属于本讲'}]
        result=project_applications(source,{'p1':'K-F01','p2':'K-F02'})
        self.assertEqual([a['id'] for a in result],['nested'])
        self.assertEqual(result[0]['knowledge_keys'],['K-F01','K-F02'])
        self.assertEqual(result[0]['answer'],'保持这份答案')
        self.assertNotIn('knowledge_keys',source[0])

    def test_revision_mismatch_is_visible(self):
        b,d=fixture();d['knowledge_revision']='other'
        self.assertIn('knowledge_revision_mismatch',{x['code'] for x in inspect(b,d)['issues']})

    def test_cross_topic_and_malformed_refs_do_not_resolve(self):
        for refs in (['K-I01'],[{'forged':'K-T01'}],None):
            b,d=fixture();d['sections'][0]['blocks'][0]['knowledge_keys']=refs
            report=inspect(b,d)
            self.assertIn('knowledge_refs',{x['code'] for x in report['issues']})
            self.assertEqual(report['explained_keys'],[])

    def test_metadata_in_summary_is_not_counted_as_explanation(self):
        b,d=fixture();d['sections'][0]['blocks'][0]['kind']='summary'
        self.assertEqual(inspect(b,d)['explained_keys'],[])

    def test_model_answer_field_is_flagged_and_does_not_replace_evidence(self):
        b,d=fixture();block=d['sections'][0]['blocks'][0]
        block.update(kind='worked_example',example_key='E-T01',answer='999')
        report=inspect(b,d)
        self.assertIn('unbound_answer_or_code',{x['code'] for x in report['issues']})
        with TemporaryDirectory() as folder:
            render(b,d,report,Path(folder))
            text=(Path(folder)/'01-数值类型转换.md').read_text(encoding='utf-8')
            self.assertIn('puts("2");',text)
            self.assertIn('```text\n2\n```',text)
            self.assertNotIn('999',text)

    def test_missing_blocks_becomes_a_reported_gap(self):
        b,d=fixture();d['sections'][0]['blocks']=None
        self.assertIn('blocks_not_array',{x['code'] for x in inspect(b,d)['issues']})

    def test_application_must_be_explained_with_its_knowledge_refs(self):
        b,d=fixture();b['applications']=[{'id':'app','knowledge_keys':['K-T01']}]
        self.assertIn('missing_application_explanation',{x['code'] for x in inspect(b,d)['issues']})
        d['sections'][0]['blocks'][0]['application_keys']=['app']
        self.assertEqual(inspect(b,d)['explained_applications'],['app'])
        d['sections'][0]['blocks'][0]['application_keys']=['other']
        self.assertIn('application_refs',{x['code'] for x in inspect(b,d)['issues']})

    def test_editorial_revision_is_not_labelled_first_model_output(self):
        b,d=fixture();d['editorial_revision']={'author':'Codex','id':'r1'}
        with TemporaryDirectory() as folder:
            render(b,d,inspect(b,d),Path(folder))
            text=(Path(folder)/'01-数值类型转换.md').read_text(encoding='utf-8')
            self.assertIn('由 Codex 定向修订',text)
            self.assertNotIn('正文为千问首次输出',text)

    def test_legacy_paragraphs_are_preserved_without_fabricated_links(self):
        b,d=fixture()
        d['sections']=[{'section_key':'legacy','heading':'原小节','paragraphs':['原段落必须保留。'],'example_keys':['E-T01'],'exercise_keys':[]}]
        with TemporaryDirectory() as folder:
            report=inspect(b,d);render(b,d,report,Path(folder))
            text=(Path(folder)/'01-数值类型转换.md').read_text(encoding='utf-8')
            self.assertIn('原段落必须保留。',text)
            self.assertIn('## 原小节',text)
            self.assertEqual(report['explained_keys'],[])
            self.assertIn('没有替模型补写引用',text)


if __name__=='__main__':unittest.main()
