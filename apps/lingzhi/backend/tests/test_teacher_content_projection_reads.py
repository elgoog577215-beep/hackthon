from copy import deepcopy
from teacher_content_projection import project_teacher_content


def test_course_reads_project_only_working_materials_without_copying_history(monkeypatch):
    import teacher_content_projection as module
    raw={'course_id':'c','course_name':'测试课','knowledge_first_workflow':'knowledge_first_generic_v1',
         'nodes':[{'node_id':'L','node_level':1,'node_name':'第1讲'},
                  {'node_id':'N','node_level':2,'parent_node_id':'L','node_name':'小节'}]}
    class History:
        def __deepcopy__(self,memo):raise AssertionError('Rendering must not copy historical jobs or revisions')
    source={'outline_revision_id':'O','jobs':{'big-history':History()},'lessons':{'L':{
        'source_state':'current','working_revision_id':'P2','working_script_revision_id':'H2',
        'revisions':[{'revision_id':'P1','historical':History()},
                     {'revision_id':'P2','plan':{'sections':[{'node_id':'N','knowledge_structure':['知识']}]}}],
        'script_revisions':[{'revision_id':'H1','historical':History()},
            {'revision_id':'H2','publication_eligible':True,'source_lesson_plan_revision_id':'P2',
             'sections':[{'section_node_id':'N','blocks':[{'block_id':'B','role':'concept','content':'已保存的完整正文'}]}]}]}}}
    expected=project_teacher_content(deepcopy(raw),authoring=source)
    class Repository:
        def load(self,*_):raise AssertionError('Course reads must use the original repository read projection')
        def read_projection(self,cid,projector):
            assert cid=='c'
            return projector(source)
    monkeypatch.setattr(module,'authoring_repository',lambda *_:Repository())
    actual=project_teacher_content(deepcopy(raw),storage=object())
    assert actual==expected
    assert actual['nodes'][1]['node_content'].endswith('已保存的完整正文')
    assert source['lessons']['L']['working_script_revision_id']=='H2'
